from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    google_api_key: str | None = None
    llm_provider: str = "mock"
    embedding_provider: str = "google"
    google_model: str = "gemini-flash-latest"
    embedding_model: str = "gemini-embedding-001"
    data_dir: Path = Path("data")
    collection_name: str = "hotels"
    request_delay_seconds: float = 1.0
    max_retries: int = 4
    embedding_batch_size: int = 32
    retrieval_limit: int = 5
    llm_fallback_confidence_threshold: float = 0.7
    vector_weight: float = 0.7
    metadata_weight: float = 0.3
    @property
    def raw_text_path(self) -> Path: return self.data_dir / "raw" / "file_hotels.txt"
    @property
    def jsonl_path(self) -> Path: return self.data_dir / "processed" / "hotels.jsonl"
    @property
    def csv_path(self) -> Path: return self.data_dir / "processed" / "hotels.csv"
    @property
    def chroma_path(self) -> Path: return self.data_dir / "processed" / "chromadb"
    @property
    def state_path(self) -> Path: return self.data_dir / "processed" / "extraction_state.json"
settings = Settings()
PROJECT_ROOT = Path.cwd()
DATA_DIR = settings.data_dir
RAW_TEXT_PATH = settings.raw_text_path
CSV_PATH = settings.csv_path
CHROMA_PATH = settings.chroma_path
EXTRACTION_STATE_PATH = settings.state_path
GOOGLE_MODEL = settings.google_model
EMBEDDING_MODEL = settings.embedding_model
MAX_RETRIES = settings.max_retries
REQUEST_DELAY_SECONDS = settings.request_delay_seconds
