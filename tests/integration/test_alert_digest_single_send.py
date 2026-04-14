from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import src.alerts.detector as detector
from src.alerts.notifier import NotificationResult
from src.db.models import Alert, ReviewAnalysis, UnifiedReview


def test_alert_detection_sends_single_digest_for_multiple_alerts(sqlite_test_db, monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 14, 8, 30, tzinfo=timezone.utc)

    session = Session(bind=sqlite_test_db)
    reviews: list[UnifiedReview] = []
    for idx in range(3):
        review = UnifiedReview(
            source="api",
            source_review_id=f"neg-{idx}",
            location_id=5,
            rating=1,
            text="Very bad service",
            author="user@example.com",
            created_at=fixed_now - timedelta(hours=idx + 2),
            ingested_at=fixed_now,
        )
        reviews.append(review)
        session.add(review)

    session.flush()
    for review in reviews:
        session.add(
            ReviewAnalysis(
                unified_review_id=review.id,
                sentiment="negative",
                categories=["servicio"],
                summary="Muy mala experiencia",
                urgency=3,
                created_at=fixed_now - timedelta(hours=1),
            )
        )

    session.commit()
    session.close()

    calls: list[dict] = []

    def fake_notify(alerts, generated, persisted, run_at):
        calls.append({"alerts": list(alerts), "generated": generated, "persisted": persisted, "run_at": run_at})
        return NotificationResult(delivered_to="slack", detail="digest_sent")

    monkeypatch.setattr(detector, "notify_alert_digest", fake_notify)

    stats = detector.run_alert_detection(now=fixed_now)

    read_session = Session(bind=sqlite_test_db)
    db_alerts = read_session.scalar(select(func.count(Alert.id)))
    read_session.close()

    assert stats.persisted >= 2
    assert db_alerts == stats.persisted
    assert len(calls) == 1
    assert calls[0]["persisted"] == stats.persisted
    assert len(calls[0]["alerts"]) == stats.persisted
