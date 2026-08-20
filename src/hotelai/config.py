"""Single settings source for the whole backend (AGENTS.md: use `settings`, no ad-hoc `os.getenv()`).

Values load from `.env` (see `.env.example`); every module below imports `settings` from
here instead of reading the environment directly, so provider keys/models/limits stay in
one place. `google_api_key`/`groq_api_key` being unset is a valid, expected state — most
of the pipeline degrades gracefully to deterministic/offline behaviour rather than raising.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    google_api_key: str | None = None
    groq_api_key: str | None = None
    llm_provider: str = "mock"
    embedding_provider: str = "google"
    google_model: str = "gemini-flash-latest"
    groq_model: str = "openai/gpt-oss-120b"
    embedding_model: str = "gemini-embedding-001"
    data_dir: Path = Path("data")
    log_dir: Path = Path("logs")
    collection_name: str = "hotels"
    request_delay_seconds: float = 1.0
    gemini_requests_per_minute: int = 5
    groq_requests_per_minute: int = 30
    max_retries: int = 4
    embedding_batch_size: int = 32
    retrieval_limit: int = 5  # hard cap on search results; MCP/API always clamp top_k to this (assignment: max 5)
    llm_fallback_confidence_threshold: float = 0.7  # below this, structured_extractor sends the record to Groq/Gemini review
    vector_weight: float = 0.7  # HotelRetriever._score blends vector similarity and metadata overlap using these two
    metadata_weight: float = 0.3
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"  # comma-separated; add the deployed frontend origin (e.g. Netlify URL) here
    llm_cache_path: Path = Path("tests/fixtures/llm_cached_responses.json")  # orphaned: no current code reads this
    @property
    def raw_text_path(self) -> Path: return self.data_dir / "raw" / "file_hotels.txt"  # unused: nothing writes this file today
    @property
    def hotel_records_path(self) -> Path: return self.data_dir / "processed" / "hotels_data.jsonl"
    @property
    def chroma_path(self) -> Path: return self.data_dir / "processed" / "chromadb"
    @property
    def state_path(self) -> Path: return self.data_dir / "processed" / "extraction_state.json"  # unused: no resume logic exists today
    @property
    def log_path(self) -> Path: return self.log_dir / "app.log"
    @property
    def cors_origins_list(self) -> list[str]: return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
settings = Settings()
