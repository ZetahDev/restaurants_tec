from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://feedbackiq:feedbackiq@localhost:5432/feedbackiq"
    )
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8081")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    timezone: str = os.getenv("TIMEZONE", "UTC")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
