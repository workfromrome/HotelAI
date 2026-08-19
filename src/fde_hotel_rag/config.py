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
    collection_name: str = "hotels"
    request_delay_seconds: float = 1.0
    gemini_requests_per_minute: int = 5
    groq_requests_per_minute: int = 30
    max_retries: int = 4
    embedding_batch_size: int = 32
    retrieval_limit: int = 5
    llm_fallback_confidence_threshold: float = 0.7
    vector_weight: float = 0.7
    metadata_weight: float = 0.3
    llm_cache_path: Path = Path("tests/fixtures/llm_cached_responses.json")
    @property
    def raw_text_path(self) -> Path: return self.data_dir / "raw" / "file_hotels.txt"
    @property
    def hotel_records_path(self) -> Path: return self.data_dir / "processed" / "hotels_data.jsonl"
    @property
    def chroma_path(self) -> Path: return self.data_dir / "processed" / "chromadb"
    @property
    def state_path(self) -> Path: return self.data_dir / "processed" / "extraction_state.json"
settings = Settings()
