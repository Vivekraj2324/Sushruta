"""
Sushruta — Application Configuration
=====================================

Centralised configuration using pydantic-settings.
All values are loaded from environment variables or .env file.

Design decisions:
- lru_cache on get_settings() ensures .env is read exactly once.
- Pydantic validates types at startup — misconfigurations fail fast.
- Defaults are tuned for local development; production overrides via env.

Phase 2 additions:
- Gemini API settings for embeddings and LLM generation.
- Chunking parameters for document processing pipeline.
- Retrieval parameters for RAG question-answering.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes
    ----------
    APP_NAME : str
        Display name used in API docs and health endpoint.
    APP_VERSION : str
        Semantic version of the current release.
    DEBUG : bool
        Enables verbose logging and auto-reload hints.
    ENVIRONMENT : str
        Runtime environment: development | staging | production.

    DATABASE_URL : str
        Async PostgreSQL connection string (asyncpg driver).

    SECRET_KEY : str
        HMAC key for JWT signing. Must be long and random in production.
    ALGORITHM : str
        JWT signing algorithm. HS256 is the standard for symmetric keys.
    ACCESS_TOKEN_EXPIRE_MINUTES : int
        Token TTL. 30 minutes balances security with usability for doctors.

    OPENAI_API_KEY : str
        OpenAI API key (retained for fallback compatibility).
    GEMINI_API_KEY : str
        Google AI Studio key for embeddings and LLM generation.

    EMBEDDING_MODEL : str
        Gemini embedding model name.
    EMBEDDING_DIMENSIONS : int
        Output vector dimensionality (768 for text-embedding-004).
    LLM_MODEL : str
        Gemini generative model for RAG responses.
    LLM_TEMPERATURE : float
        Sampling temperature for generation (0.2 = focused/factual).

    CHUNK_SIZE : int
        Target chunk size in characters for document splitting.
    CHUNK_OVERLAP : int
        Overlap between consecutive chunks to preserve context.
    RAG_TOP_K : int
        Number of chunks to retrieve for context assembly.

    UPLOAD_DIR : str
        Local directory where uploaded medical files are stored.
    MAX_FILE_SIZE_MB : int
        Maximum allowed upload size in megabytes.
    ALLOWED_FILE_TYPES : list[str]
        MIME-type-style extensions permitted for upload.

    DB_POOL_SIZE : int
        SQLAlchemy connection pool size.
    DB_MAX_OVERFLOW : int
        Maximum overflow connections above pool_size.
    """

    # ── Application ──────────────────────────────────────────────
    APP_NAME: str = "Sushruta"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # ── Database ─────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://sushruta:sushruta_dev_password@localhost:5432/sushruta"

    # ── JWT Authentication ───────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-a-64-char-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── AI / Gemini (Phase 2) ────────────────────────────────────
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""  # Retained for fallback compatibility

    # ── Embedding Config ─────────────────────────────────────────
    EMBEDDING_MODEL: str = "models/text-embedding-004"
    EMBEDDING_DIMENSIONS: int = 768
    LLM_MODEL: str = "gemini-2.0-flash"
    LLM_TEMPERATURE: float = 0.2

    # ── Chunking Config ──────────────────────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 5

    # ── File Upload ──────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_FILE_TYPES: list[str] = [
        ".pdf", ".png", ".jpg", ".jpeg", ".docx",
    ]

    # ── Connection Pooling ───────────────────────────────────────
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── Pydantic Settings Config ─────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore unknown env vars
    )

    @property
    def max_file_size_bytes(self) -> int:
        """Convert MB limit to bytes for upload validation."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


@lru_cache()
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Why lru_cache?
    - .env is read from disk once, not on every request.
    - All downstream code shares the same settings object.
    - In tests, this can be overridden via dependency_overrides.
    """
    return Settings()
