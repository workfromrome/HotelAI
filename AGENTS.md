# AGENTS.md

## System overview

- `src/ingestion/`: PDF loading/segmentation and structured Gemini extraction.
  - `pdf_parser.py`: detects hotel blocks and applies limited OCR cleanup.
  - `structured_extractor.py`: canonical `HotelRecord` extraction and CSV export.
- `src/search/`: embeddings, ChromaDB indexing, hybrid retrieval and Markdown formatting.
  - `vector_store.py`: `GeminiEmbedder`, offline embedder and persistent Chroma index.
  - `retriever.py`: maximum-five-result search and ranking.
- `src/mcp_server/server.py`: canonical FastMCP server and `search_hotels(query)` tool.
- `src/fde_hotel_rag/`: configuration, canonical schema, storage/protocols and temporary legacy compatibility wrappers.
- `scripts/run_pipeline.py`: primary ingestion entry point; `--offline` skips API calls and indexing.
- `tests/`: unit/integration-style tests for parsing, extraction, Chroma, retrieval and MCP.

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
- Never log, print, commit or include `GOOGLE_API_KEY` or `.env` contents.
- Do not add hotel names/locality lists or provider-specific constants outside configuration.
- Use `settings` from `src/fde_hotel_rag/config.py`; do not add new `os.getenv()` calls in application modules.

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

## Known gotchas and technical debt

- The PDF currently yields 39 pages and 19 hotel blocks; the first page is introductory.
- OCR artifacts exist in real headings, including `GATTAREL!`, `PA!CE`, `DANIE"`, `CINTO"` and `VIL!GGIO`.
- `gemini-flash-latest` is the generative model. `gemini-embedding-001` is the embedding model; `text-embedding-004` returned 404 and must not be restored as the default.
- Offline embeddings are deterministic test doubles, not semantically equivalent to Gemini embeddings.
- Real Gemini/Chroma checks require network access, a valid `GOOGLE_API_KEY` and available quota. Offline success does not prove online success.
- The MCP server should be started with `python -m mcp_server.server` and must have a configured/indexed retriever in production.
- `src/fde_hotel_rag/` still contains legacy compatibility code. Prefer `ingestion/`, `search/` and `mcp_server/` for new logic.
- Current tests include integration-style work against the real PDF and can be slow. Avoid adding repeated PDF/Chroma setup; use fixtures and mocks for unit tests.
