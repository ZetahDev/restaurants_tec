from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import UnifiedReview
from src.etl.loader import upsert_unified_reviews
from src.etl.schemas import UnifiedReviewInput


def test_unified_review_upsert_is_idempotent(sqlite_test_db) -> None:
    session = Session(bind=sqlite_test_db)
    rows = [
        UnifiedReviewInput(
            source="api",
            source_review_id="same-id",
            location_id=1,
            rating=2,
            text="Original text",
            author="User",
            created_at="2026-04-13T10:00:00+00:00",
        )
    ]

    upsert_unified_reviews(session=session, rows=rows)
    session.commit()

    updated_rows = [
        UnifiedReviewInput(
            source="api",
            source_review_id="same-id",
            location_id=1,
            rating=1,
            text="Updated text",
            author="User",
            created_at="2026-04-13T10:00:00+00:00",
        )
    ]
    upsert_unified_reviews(session=session, rows=updated_rows)
    session.commit()

    count = session.scalar(select(func.count(UnifiedReview.id)))
    review = session.scalar(select(UnifiedReview).where(UnifiedReview.source_review_id == "same-id"))

    assert count == 1
    assert review is not None
    assert review.text == "Updated text"
    assert review.rating == 1
