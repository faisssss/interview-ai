"""Application settings, read from environment variables and backend/.env."""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    database_url: str = "postgresql+asyncpg://meetings:meetings@localhost:5432/meetings"
    storage_dir: Path = Path("data")
    cors_origins: list[str] = ["http://localhost:3000"]

    # Providers: "local" runs models on this machine, "fake" returns canned results.
    asr_provider: Literal["local", "fake"] = "local"
    diarization_provider: Literal["local", "fake"] = "local"
    llm_provider: Literal["claude", "fake"] = "claude"
    ml_device: Literal["cuda", "cpu"] = "cuda"
    asr_model: str = "large-v3-turbo"
    asr_batch_size: int = 8
    hf_token: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    llm_model_extract: str = "claude-opus-5-5"
    llm_effort_extract: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    timezone: str = "Asia/Kolkata"

    max_upload_mb: int = 500
    max_duration_minutes: int = 180

    job_max_attempts: int = 3
    job_stale_minutes: int = 10
    heartbeat_seconds: float = 30.0
    worker_poll_seconds: float = 5.0


@cache
def get_settings() -> Settings:
    return Settings()
