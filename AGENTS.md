# AGENTS.md

## System overview

- `src/ingestion/`: PDF loading/segmentation and structured Groq/Gemini-reviewed extraction.
  - `pdf_parser.py`: pdfplumber-based hotel-block segmentation, OCR cleanup, and word bounding boxes (used as the reference `.words` source for the visual-ratings fallback).
  - `pymupdf_parser.py`: font-size-aware header extractor; canonical `nome`/`localita` source for `structured_extractor`. The two flat exclusion word-lists (`_EXCLUDED_HEADER_TEXT`, `_EXCLUDED_BADGE_WORDS`) live as one-word-per-line `.txt` files in `pdf_artifacts/`, not as Python constants — edit those files to add/remove excluded words, no code change needed. `_STOP_MARKERS` (regex) and `_LIGATURE_GLYPHS` (character-substitution rule) stayed in code: they're parsing logic, not data.
  - `structured_extractor.py`: canonical `HotelRecord` extraction and CSV/JSONL export.
- `src/search/`: embeddings, ChromaDB indexing, hybrid retrieval and Markdown formatting.
  - `vector_store.py`: `GeminiEmbedder`, offline embedder and persistent Chroma index. `build_index_from_csv` reads `hotels_data.csv` back via `structured_extractor.read_csv` and is the real Part-1-to-Part-2 bridge — `build_index` itself takes only records, no PDF blocks, since the document text embedded per hotel is `record.source.raw_text`, already present in the CSV's `source` column.
  - `retriever.py`: maximum-five-result search and ranking.
- `src/rag/rag_engine.py`: `RAGEngine`/`answer_query` conversational synthesis over `HotelRetriever` results; tries Groq first, falls back to Gemini, then to the fixed fallback string `FALLBACK_MESSAGE`. Not yet wired into `mcp_server`.
- `src/mcp_server/server.py`: canonical FastMCP server and `search_hotels(query)` tool. Does not yet expose the RAG engine's natural-language synthesis, only raw retrieval.
- `src/api/main.py`: FastAPI HTTP layer for the React frontend — `POST /api/chat` (`RAGEngine.answer_query`), `GET /api/hotels` (reads `settings.hotel_records_path`, i.e. `data/processed/hotels_data.jsonl`, the canonical `HotelRecord`-schema export — not the legacy `hotels.jsonl`), `GET /api/health` (Chroma connectivity/count + Groq/Gemini key presence). Retriever/RAG-engine access is via `Depends(get_retriever)`/`Depends(get_rag_engine)`, overridable in tests; the real Chroma index is only built in the `lifespan` startup hook, so tests never touch it unless they opt in. CORS is open to `http://localhost:5173` (Vite dev server) only. Run: `uvicorn api.main:app --reload --port 8000` (`PYTHONPATH=src`, from repo root).
- `frontend/`: Vite + React chatbot UI (dark theme, ChatGPT/Claude-style layout). Talks to the backend via `/api/*`, proxied to `localhost:8000` by `vite.config.js` in dev — CORS is also configured on the backend as a second line of defense. `src/components/`: `Sidebar.jsx` (status, 5 quick queries, hotel catalog accordion), `ChatArea.jsx` (hero view, message bubbles, page-range citation badges, typing indicator), `InputBar.jsx`. `src/styles/app.css` holds the whole design (CSS variables for the zinc/emerald palette). No markdown renderer is wired in — assistant answers render as `white-space: pre-wrap` plain text, so literal `**bold**`/table-pipe markup from the LLM is visible as-is; add `react-markdown` if that needs to render properly. Run: `cd frontend && npm install && npm run dev` (port 5173). `.claude/launch.json` has a `frontend` config for the `preview_start` tool.
- `src/hotelai/`: canonical `settings`/`Settings` (config.py), `HotelRecord` schema (schemas.py), centralized logging setup (logging_setup.py), `prompts/` (LLM prompt text as `.md` files plus `load_prompt(name)`, see line below), and `server.py` (deprecated compat wrapper, see line below). Renamed from `fde_hotel_rag`; the project folder itself is still named `fde_hotel_rag` pending a manual rename by the user (see Known gotchas). Formerly also held `extractors/`/`storage/` subpackages — deleted, they contained no source, only stale `__pycache__`.
- `src/hotelai/prompts/`: all LLM prompt text lives here as `.md` files, not inline in Python — `load_prompt(name)` reads `<name>.md` and strips it; callers `.format(...)` it themselves when the template has placeholders (`conversational_rag.md` takes `{fallback_message}`, `structured_review.md` takes `{example}`, the dynamically-built `HotelReview` JSON sample). `visual_ratings.md` has no placeholders. Editing a prompt's wording only ever means editing the `.md` file.
- `scripts/run_pipeline.py`: primary ingestion entry point; `--offline` skips API calls and indexing.
- `tests/`: unit/integration-style tests for parsing, extraction, Chroma, retrieval, MCP and the FastAPI layer (`test_api.py`, 100% mocked via `app.dependency_overrides`).
- `scripts/compare_pdf_extractors.py`: comparison-only PyMuPDF extraction benchmark.

Canonical flow:

```text
PDF -> ingestion -> HotelRecord -> CSV/JSONL -> [CSV re-read] -> Gemini embeddings -> ChromaDB -> retriever -> FastMCP
```

`run_pipeline.py` writes the CSV, then re-reads it with `read_csv` before calling `build_index_from_csv` — indexing never touches the in-memory `records` from extraction directly. See `presentation-notes/csv-driven-indexing.md` (local-only, gitignored) for why this round trip exists instead of indexing straight from memory.

## Code standards

- Python 3.11+; use type hints on public functions, protocols and class methods.
- Use Pydantic models for data crossing module boundaries. `src/hotelai/schemas.py` is the canonical schema source.
- Prefer small modules, dependency injection and `typing.Protocol` over concrete provider coupling.
- Use `snake_case` for functions/variables, `PascalCase` for classes, and descriptive Italian user-facing errors.
- Keep formatting simple and readable; avoid compressed one-line statements for new code.
- Catch only expected exceptions where possible. Convert provider failures into actionable Italian `RuntimeError` messages.
- Never log, print, commit or include `GOOGLE_API_KEY`, `GROQ_API_KEY` or `.env` contents.
- Do not add hotel names/locality lists or provider-specific constants outside configuration.
- Use `settings` from `src/hotelai/config.py`; do not add new `os.getenv()` calls in application modules.
- LLM prompt text (system prompts, instruction strings sent as `contents`) belongs in `src/hotelai/prompts/*.md`, loaded via `hotelai.prompts.load_prompt`; do not inline new prompt strings in Python.
- The structured-extraction LLM review cascade (`_review_with_llm` in `structured_extractor.py`) tries Groq first (`openai/gpt-oss-120b`, JSON Schema via `response_format`), then Gemini (`response_schema=HotelRecord`) as fallback; it never raises — on total failure it tags the record with the `review_llm_non_disponibile` issue and returns the deterministic (`_offline`) extraction unchanged. It only runs when `_needs_llm_fallback` is true, i.e. when the deterministic record's `quality.confidence` (the minimum of its per-field confidences) is below `settings.llm_fallback_confidence_threshold`.
- Testing tiers (do not blur these): (1) routine `pytest` must be 100% mocked, 0 API calls; (2) any live-API script/diagnostic runs only on explicit user request, never automatically or repeatedly. `tests/fixtures/llm_cached_responses.json` / `settings.llm_cache_path` are currently orphaned — nothing under `src/` reads them since the module that used them (title correction) was removed; treat them as dead until something consumes them again, and don't wire up a new caller without updating this note.
- `RAGEngine.answer_query` uses the same Groq-first/Gemini-fallback cascade as title correction, but as a single synchronous attempt per provider (no sleep-based retry/backoff, since it is on the interactive query path, not a batch job). On empty query, empty retrieval results, or both providers failing/unavailable it returns `FALLBACK_MESSAGE` (`"Informazione non sufficiente nei documenti forniti"`) with `is_fallback=True` and never raises.
- `CONVERSATIONAL_RAG_PROMPT` (was `RAG_SYSTEM_PROMPT`) asks for a warm, discursive concierge tone with bolded hotel names in a bullet list and explicitly forbids Markdown pipe tables (`|...|`) — the frontend's `react-markdown` table styling still exists for whatever the model actually returns, but is no longer the expected shape. Page citations (`[Pag. x-y]`) stay inline per hotel; the frontend strips these from rendered prose (`stripPageCitations`) since the page badges already show them.

## Workflow for significant changes

For important, non-trivial changes (new features, architectural changes, breaking changes — not small fixes or tweaks), follow this sequence using the project's installed skills, in order:

1. `/wayfinder` — chart the work as decision tickets before committing to an approach; use for anything too big or too foggy for a single planning pass.
2. `/grill-with-docs` — stress-test the resulting plan/design via a relentless interview; also produces ADRs/glossary entries as a side effect.
3. `/writing-plans` — turn the sharpened decisions into a concrete, step-by-step implementation plan.
4. `/implement` — execute the plan (TDD where possible, regular test/typecheck runs, `/code-review` before commit).

Do not skip straight to implementation for changes of this size; small/local fixes do not need this pipeline.

## Execution guardrails

Do not touch:

- `data/raw/FileHotels.pdf` (read-only source PDF, provided with the assignment; never modify or delete).
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
& .\.venv\Scripts\python.exe -m ingestion.pdf_parser "data\raw\FileHotels.pdf"
& .\.venv\Scripts\python.exe -m ingestion.structured_extractor `
  "data\raw\FileHotels.pdf" "data\processed\hotels_data.csv" --offline
```

Offline pipeline check:

```powershell
$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe scripts\run_pipeline.py "data\raw\FileHotels.pdf" --offline
```

Expected offline result: 19 hotel records and no API call. There is no configured linter or type checker; do not claim lint/type validation unless one is added and executed.

Web app (backend + frontend):

```powershell
$env:PYTHONPATH = "src"
& .\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
```

```powershell
cd frontend
npm install
npm run dev
```

Verified 2026-08-18: with the real indexed Chroma collection and both `GROQ_API_KEY`/`GOOGLE_API_KEY` configured, `GET /api/health` reports `status: "ok"`, `GET /api/hotels` returns the 19 canonical records, and `POST /api/chat` returns real Groq-generated answers with correct `[Pag. x-y]` citations end to end through the React UI (desktop and the mobile off-canvas sidebar). `tests/test_api.py` covers the same endpoints with `app.dependency_overrides` (zero network calls, per the testing tiers in `AGENTS.md`/memory).

## Known gotchas and technical debt

- The PDF currently yields 39 pages and 19 hotel blocks; the first page is introductory.
- OCR artifacts exist in real headings, including `GATTAREL!`, `PA!CE`, `DANIE"`, `CINTO"` and `VIL!GGIO`.
- `gemini-flash-latest` is the generative model. `gemini-embedding-001` is the embedding model; `text-embedding-004` returned 404 and must not be restored as the default.
- Offline embeddings are deterministic test doubles, not semantically equivalent to Gemini embeddings.
- Real Gemini/Chroma checks require network access, a valid `GOOGLE_API_KEY` and available quota. Offline success does not prove online success.
- The current project quota was observed at 5 `generate_content` requests/minute for the active Gemini model; a 503 or 429 can still occur even with client-side throttling.
- PyMuPDF's font-size-aware header parsing (`pymupdf_parser.py`) is the canonical `nome`/`localita` source; `pdf_parser.py`'s own segmentation only supplies the reference word bounding boxes used by the visual-ratings fallback.
- `HotelBlock` contains title, pages, text, word bounding boxes, and locality. Preserve these when creating replacement blocks.
- `HotelRecord` supports `categoria_ufficiale`, structured `valutazioni`, `qualificatori`, `source`, and `quality`; numeric scores must remain `null` when not readable.
- The MCP server should be started with `python -m mcp_server.server` and must have a configured/indexed retriever in production.
- `src/hotelai/` still contains legacy compatibility code. Prefer `ingestion/`, `search/` and `mcp_server/` for new logic.
- Current tests include integration-style work against the real PDF and can be slow. Avoid adding repeated PDF/Chroma setup; use fixtures and mocks for unit tests.
- 2026-08-20: the Python package `fde_hotel_rag` was renamed to `hotelai` (imports, `pyproject.toml`, docs) as part of a project rename to "HotelAI". The project's root folder on disk (currently `.../fde_hotel_rag`) was intentionally left as-is — the user will rename it manually outside this session, since doing it mid-session would break the working directory the agent is rooted in. Once that happens, this note and any remaining absolute paths under `fde_hotel_rag\` in docs/config should be revisited.
- `structured_extractor.read_csv` is the inverse of `write_csv`; keep the two symmetric. If a new `HotelRecord` field is added, decide whether it needs a parsing rule in `read_csv`'s `_CSV_*_FIELDS` tuples (JSON list/dict, int, or bool) — plain strings need no rule.
