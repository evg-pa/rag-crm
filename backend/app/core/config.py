"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "RAG-CRM"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://rag_user:rag_pass@localhost:5432/rag_crm"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM — DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # Ollama (local fallback)
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384

    # Reranker
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # LLM defaults
    LLM_TEMPERATURE: float = 0.0

    # CRM Connector
    CRM_ADAPTER: str = "mock"  # "mock" or "rest"
    CRM_SYNC_FREQUENCY: str = "hourly"  # hourly | daily | manual
    CRM_RAG_BRIDGE: bool = False  # If true, create Document+Chunk from CRM entities
    CRM_REST_BASE_URL: str = ""  # Base URL for the REST CRM adapter
    CRM_REST_API_KEY: str = ""  # API key for the REST CRM adapter

    # Auth
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
