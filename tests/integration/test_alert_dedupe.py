from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.alerts.detector import run_alert_detection
from src.db.models import Alert, UnifiedReview


def test_alert_deduplication_by_window_rule_and_location(sqlite_test_db, monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 14, 12, 30, tzinfo=timezone.utc)

    session = Session(bind=sqlite_test_db)
    session.add(
        UnifiedReview(
            source="survey",
            source_review_id="3000",
            location_id=3,
            rating=2,
            text="Poor quality and slow service",
            author="user@example.com",
            created_at=fixed_now - timedelta(days=1),
            ingested_at=fixed_now,
        )
    )
    session.commit()
    session.close()

    stats_first = run_alert_detection(now=fixed_now)
    stats_second = run_alert_detection(now=fixed_now)

    read_session = Session(bind=sqlite_test_db)
    total_alerts = read_session.scalar(select(func.count(Alert.id)))
    read_session.close()

    assert stats_first.persisted == 1
    assert stats_second.persisted == 0
    assert total_alerts == 1
