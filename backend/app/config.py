"""
Application settings — all values sourced from environment variables.

At production startup, Vault populates these env vars before uvicorn launches.
No default credentials are ever hardcoded here.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Celery broker + result backend (both point at Redis)
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0", alias="CELERY_BROKER_URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0", alias="CELERY_RESULT_BACKEND"
    )

    # MLflow
    mlflow_tracking_uri: str = Field(
        default="http://localhost:5001", alias="MLFLOW_TRACKING_URI"
    )
    model_alias: str = Field(default="Production", alias="MODEL_ALIAS")
    captioner_model_name: str = Field(
        default="captioner", alias="CAPTIONER_MODEL_NAME"
    )
    storyteller_model_name: str = Field(
        default="storyteller", alias="STORYTELLER_MODEL_NAME"
    )

    # Ollama
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )

    # MinIO / S3 (injected by Vault at runtime — no defaults for credentials)
    minio_endpoint_url: str = Field(
        default="http://localhost:9000", alias="MINIO_ENDPOINT_URL"
    )
    minio_access_key: str = Field(default="", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="", alias="MINIO_SECRET_KEY")

    # Image validation
    max_image_bytes: int = Field(default=5 * 1024 * 1024, alias="MAX_IMAGE_BYTES")  # 5 MB
    min_std_deviation: float = Field(
        default=5.0, alias="MIN_STD_DEVIATION"
    )  # blank-image threshold

    # PostgreSQL (used by human_review node)
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/comicdb",
        alias="DATABASE_URL",
    )

    # CORS — comma-separated list of allowed origins
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    model_config = {"env_file": ".env", "populate_by_name": True}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
