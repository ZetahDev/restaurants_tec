from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from src.db.models import DeadLetterEvent, UnifiedReview
from src.etl.schemas import UnifiedReviewInput


def _upsert_insert_statement(session: Session):
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        return pg_insert(UnifiedReview)
    if dialect == "sqlite":
        return sqlite_insert(UnifiedReview)
    raise ValueError(f"Unsupported dialect for upsert: {dialect}")


def upsert_unified_reviews(session: Session, rows: list[UnifiedReviewInput]) -> int:
    if not rows:
        return 0

    now_utc = datetime.now(timezone.utc)
    values = [
        {
            "source": row.source,
            "source_review_id": row.source_review_id,
            "location_id": row.location_id,
            "rating": row.rating,
            "text": row.text,
            "author": row.author,
            "created_at": row.created_at,
            "ingested_at": now_utc,
        }
        for row in rows
    ]

    insert_stmt = _upsert_insert_statement(session).values(values)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["source", "source_review_id"],
        set_={
            "location_id": insert_stmt.excluded.location_id,
            "rating": insert_stmt.excluded.rating,
            "text": insert_stmt.excluded.text,
            "author": insert_stmt.excluded.author,
            "created_at": insert_stmt.excluded.created_at,
            "ingested_at": insert_stmt.excluded.ingested_at,
        },
    )
    session.execute(upsert_stmt)
    return len(rows)


def write_dead_letter(
    session: Session,
    stage: str,
    source: str,
    payload: dict[str, Any],
    error: str,
) -> None:
    session.add(
        DeadLetterEvent(
            stage=stage,
            source=source,
            payload=payload,
            error=error,
        )
    )
