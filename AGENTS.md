# AGENTS.md

## System overview

- `src/ingestion/`: PDF loading/segmentation and structured Gemini extraction.
  - `pdf_parser.py`: detects hotel blocks and applies limited OCR cleanup.
  - `pymupdf_parser.py`: comparative layout extractor with confidence scoring.
  - `gemini_title_corrector.py`: targeted title correction for `needs_review` blocks; tries Groq (`openai/gpt-oss-120b`, default) first, then falls back to Gemini.
  - `quality_model.py`: cross-extractor confidence and review decision.
  - `structured_extractor.py`: canonical `HotelRecord` extraction and CSV/JSONL export.
- `src/search/`: embeddings, ChromaDB indexing, hybrid retrieval and Markdown formatting.
  - `vector_store.py`: `GeminiEmbedder`, offline embedder and persistent Chroma index.
  - `retriever.py`: maximum-five-result search and ranking.
- `src/rag/rag_engine.py`: `RAGEngine`/`answer_query` conversational synthesis over `HotelRetriever` results; tries Groq first, falls back to Gemini, then to the fixed fallback string `FALLBACK_MESSAGE`. Not yet wired into `mcp_server`.
- `src/mcp_server/server.py`: canonical FastMCP server and `search_hotels(query)` tool. Does not yet expose the RAG engine's natural-language synthesis, only raw retrieval.
- `src/fde_hotel_rag/`: configuration, canonical schema, storage/protocols and temporary legacy compatibility wrappers.
- `scripts/run_pipeline.py`: primary ingestion entry point; `--offline` skips API calls and indexing.
- `tests/`: unit/integration-style tests for parsing, extraction, Chroma, retrieval and MCP.
- `scripts/compare_pdf_extractors.py`: comparison-only PyMuPDF extraction benchmark.
- `scripts/run_title_ab_benchmark.py`: writes deterministic and LLM title outputs for A/B review.

Canonical flow:

```text
PDF -> ingestion -> HotelRecord -> CSV/JSONL -> Gemini embeddings -> ChromaDB -> retriever -> FastMCP
```

## Code standards

- Python 3.11+; use type hints on public functions, protocols and class methods.
- Use Pydantic models for data crossing module boundaries. `src/fde_hotel_rag/schemas.py` is the canonical schema source.
- Prefer small modules, dependency injection and `typing.Protocol` over concrete provider coupling.
- Use `snake_case` for functions/variables, `PascalCase` for classes, and descriptive Italian user-facing errors.
- Keep formatting simple and readable; avoid compressed one-line statements for new code.
- Catch only expected exceptions where possible. Convert provider failures into actionable Italian `RuntimeError` messages.
- Never log, print, commit or include `GOOGLE_API_KEY`, `GROQ_API_KEY` or `.env` contents.
- Do not add hotel names/locality lists or provider-specific constants outside configuration.
- Use `settings` from `src/fde_hotel_rag/config.py`; do not add new `os.getenv()` calls in application modules.
- Title correction uses `GeminiTitleCorrectionPayload` as the shared response schema for both providers; do not pass audit models containing open-ended dictionaries as a provider schema.
- `correct_hotel_title` first checks `settings.llm_cache_path` (`tests/fixtures/llm_cached_responses.json`, keyed by raw title) for a previously-captured real response; on a hit it returns immediately with zero API calls. On a cache miss it tries Groq first (default, `openai/gpt-oss-120b`, JSON Schema mode), then Gemini as fallback, then the raw title. Each provider retries only `429`/`503` with its own backoff timer derived from its own configured RPM (`min_interval = 60 / rpm`, delays `min_interval * 2^attempt` for 3 attempts) — Groq's 30 RPM and Gemini's 5 RPM never share a schedule. After a provider's retries are exhausted it logs a warning and the cascade moves to the next provider; after all providers fail it returns the raw title and logs a warning. It never raises.
- Testing tiers (do not blur these): (1) routine `pytest` must be 100% mocked, 0 API calls; (2) `tests/fixtures/llm_cached_responses.json` holds real captured Groq responses keyed by raw title, used to exercise the real `correct_hotel_title` code path (schema parsing, quality update) without network — regenerate it only with explicit user approval, since that requires live calls; (3) `scripts/run_title_ab_benchmark.py` and any other live-API script/diagnostic run only on explicit user request, never automatically or repeatedly.
- `RAGEngine.answer_query` uses the same Groq-first/Gemini-fallback cascade as title correction, but as a single synchronous attempt per provider (no sleep-based retry/backoff, since it is on the interactive query path, not a batch job). On empty query, empty retrieval results, or both providers failing/unavailable it returns `FALLBACK_MESSAGE` (`"Informazione non sufficiente nei documenti forniti"`) with `is_fallback=True` and never raises.

## Execution guardrails

Do not touch:

- `C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf` (read-only source; never modify or delete).
- `.env`, except with explicit user permission; use `.env.example` for documented configuration changes.
- Existing generated data unless the task explicitly requires regeneration.
- Git history, branches or unrelated user changes.

Before deleting legacy modules, search all imports and preserve a compatibility wrapper until tests and entry points no longer depend on them.

Breaking changes require:

1. updating README and `.env.example`;
2. adding/updating tests;
3. running the full validation checklist;
4. documenting any online verification that could not run.

Work incrementally: one structural refactor at a time, with tests after each step.

## Validation checklist

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m pytest -q
```

Offline PDF/parser check:

```powershell
$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m ingestion.pdf_parser `
  "C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf"
& .\.venv\Scripts\python.exe -m ingestion.structured_extractor `
  "C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf" `
  "data\processed\hotels_data.csv" --offline
```

Offline pipeline check:

```powershell
$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe scripts\run_pipeline.py `
  "C:\Users\olso4\Downloads\FDE_test\FDE_test\FileHotels.pdf" --offline
```

Expected offline result: 19 hotel records and no API call. There is no configured linter or type checker; do not claim lint/type validation unless one is added and executed.

Real title A/B benchmark:

```powershell
$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe scripts\run_title_ab_benchmark.py
```

The benchmark writes `data/processed/records_without_llm.json` and `data/processed/records_with_llm.json`. It calls Gemini only for PyMuPDF blocks with `quality.needs_review == True`. Respect the configured 5 RPM limit; do not rerun repeatedly when the project quota is exhausted.

## Known gotchas and technical debt

- The PDF currently yields 39 pages and 19 hotel blocks; the first page is introductory.
- OCR artifacts exist in real headings, including `GATTAREL!`, `PA!CE`, `DANIE"`, `CINTO"` and `VIL!GGIO`.
- `gemini-flash-latest` is the generative model. `gemini-embedding-001` is the embedding model; `text-embedding-004` returned 404 and must not be restored as the default.
- Offline embeddings are deterministic test doubles, not semantically equivalent to Gemini embeddings.
- Real Gemini/Chroma checks require network access, a valid `GOOGLE_API_KEY` and available quota. Offline success does not prove online success.
- The current project quota was observed at 5 `generate_content` requests/minute for the active Gemini model; a 503 or 429 can still occur even with client-side throttling. The A/B benchmark has not been declared complete when `records_with_llm.json` is missing.
- The Gemini free tier also enforces a separate daily cap (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, observed limit 20/day for `gemini-flash-latest`, reported internally as `gemini-3.7-flash`), independent from the 5 RPM limit. This is why Groq (`openai/gpt-oss-120b`, free-tier 30 RPM / 1,000 RPD observed 2026-08-17) is the default title-correction provider and Gemini is only the fallback; see `data/processed/title_ab_benchmark_report.md` for the real run that hit the Gemini cap on 2026-08-17 before Groq was added.
- `GROQ_API_KEY` is required for the default title-correction path; without it (or on exhausted Groq retries) the corrector falls back to Gemini, and without either key it falls back to the raw title.
- PyMuPDF currently recognizes the same 19 blocks as pdfplumber but does not improve extraction when substituted naively. Use it as a layout/coordinate comparison extractor until header block parsing is improved.
- `HotelBlock` contains lines, word bounding boxes, source pages, and optional `quality`, `header_raw_text`, and `page_num` metadata. Preserve these when creating replacement blocks.
- `HotelRecord` supports `categoria_ufficiale`, structured `valutazioni`, `qualificatori`, `source`, and `quality`; numeric scores must remain `null` when not readable.
- `data/processed/acceptance_queries_real.md` contains real retrieval query outputs and an offline extraction review table. It is a review artifact, not ground truth.
- `data/processed/pdf_extractors_comparison.md` records the current pdfplumber/PyMuPDF comparison.
- The MCP server should be started with `python -m mcp_server.server` and must have a configured/indexed retriever in production.
- `src/fde_hotel_rag/` still contains legacy compatibility code. Prefer `ingestion/`, `search/` and `mcp_server/` for new logic.
- Current tests include integration-style work against the real PDF and can be slow. Avoid adding repeated PDF/Chroma setup; use fixtures and mocks for unit tests.
