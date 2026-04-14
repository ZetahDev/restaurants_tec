from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from src.core.config import get_settings
from src.core.db import session_scope
from src.etl.extractors import fetch_api_reviews, fetch_recent_surveys
from src.etl.loader import upsert_unified_reviews, write_dead_letter
from src.etl.schemas import UnifiedReviewInput
from src.etl.transformers import transform_api_review, transform_survey_row


@dataclass
class ETLStats:
    api_extracted: int = 0
    survey_extracted: int = 0
    transformed: int = 0
    loaded: int = 0
    dead_letters: int = 0
    errors: list[str] = field(default_factory=list)


def _default_since() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=7)


def run_etl(since: datetime | None = None) -> ETLStats:
    settings = get_settings()
    since_utc = since or _default_since()
    stats = ETLStats()

    with session_scope() as session:
        api_rows: list[dict] = []
        survey_rows: list[dict] = []

        try:
            api_rows = fetch_api_reviews(
                api_base_url=settings.api_base_url,
                location_ids=range(1, 16),
                since=since_utc,
            )
            stats.api_extracted = len(api_rows)
        except Exception as exc:
            stats.errors.append(f"api extraction failed: {exc}")
            write_dead_letter(
                session=session,
                stage="extract",
                source="api",
                payload={"since": since_utc.isoformat()},
                error=str(exc),
            )
            stats.dead_letters += 1

        try:
            survey_rows = fetch_recent_surveys(session=session, since=since_utc)
            stats.survey_extracted = len(survey_rows)
        except Exception as exc:
            stats.errors.append(f"survey extraction failed: {exc}")
            write_dead_letter(
                session=session,
                stage="extract",
                source="survey",
                payload={"since": since_utc.isoformat()},
                error=str(exc),
            )
            stats.dead_letters += 1

        unified_rows: list[UnifiedReviewInput] = []

        for row in api_rows:
            try:
                unified_rows.append(transform_api_review(row))
            except ValidationError as exc:
                write_dead_letter(
                    session=session,
                    stage="transform",
                    source="api",
                    payload=row,
                    error=str(exc),
                )
                stats.dead_letters += 1

        for row in survey_rows:
            try:
                unified_rows.append(transform_survey_row(row))
            except ValidationError as exc:
                write_dead_letter(
                    session=session,
                    stage="transform",
                    source="survey",
                    payload=row,
                    error=str(exc),
                )
                stats.dead_letters += 1

        stats.transformed = len(unified_rows)
        stats.loaded = upsert_unified_reviews(session=session, rows=unified_rows)

    return stats
