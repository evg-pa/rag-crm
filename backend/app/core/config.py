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
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600  # seconds — recycle connections after 1 hour

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_MAX_CONNECTIONS: int = 20

    # LLM — DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # LLM — generic (any OpenAI-compatible provider)
    # Overrides DEEPSEEK_* when set
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    # Ollama (local fallback)
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384

    # ONNX Runtime session options
    ONNX_GRAPH_OPTIMIZATION_LEVEL: str = "all"  # "all", "basic", "extended", or "disable"
    ONNX_INTRA_OP_THREADS: int = 0  # 0 = auto (use all cores)
    ONNX_INTER_OP_THREADS: int = 0  # 0 = auto

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 50  # Maximum file upload size in megabytes

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

    # Vector store
    VECTOR_STORE: str = "pgvector"  # "pgvector" or "qdrant"
    QDRANT_URL: str = "http://localhost:6333"

    # Auth
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
