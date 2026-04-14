from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql+psycopg://feedbackiq:feedbackiq@localhost:5432/feedbackiq"
        )
    )
    api_base_url: str = field(default_factory=lambda: os.getenv("API_BASE_URL", "http://localhost:8081"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    slack_webhook_url: str = field(default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL", ""))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "UTC"))
    report_html_path: str = field(default_factory=lambda: os.getenv("REPORT_HTML_PATH", "docs/weekly_report.html"))
    report_pdf_path: str = field(default_factory=lambda: os.getenv("REPORT_PDF_PATH", "docs/weekly_report.pdf"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
