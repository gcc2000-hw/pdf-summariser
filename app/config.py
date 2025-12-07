from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    OPENAI_API_KEY: str = ""
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: List[str] = ["pdf"]
    UPLOAD_DIR: str = "uploads"
    DEFAULT_SUMMARY_MODE: str = "detailed"
    ENABLE_TABLE_EXTRACTION: bool = True
    ENABLE_ENTITY_EXTRACTION: bool = True
    DEFAULT_LLM_BACKEND: str = "openai"
    HUGGINGFACE_MODEL: str = "facebook/bart-large-cnn"
    class Config:
        env_file = ".env"
        case_sensitive = True
settings = Settings()