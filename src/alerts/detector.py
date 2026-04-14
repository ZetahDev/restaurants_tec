from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.alerts.notifier import notify_alert_digest
from src.core.db import session_scope
from src.db.models import Alert, ReviewAnalysis, UnifiedReview


@dataclass
class AlertCandidate:
    severity: str
    location_id: int
    message: str
    rule_code: str
    window_start: datetime
    window_end: datetime


@dataclass
class AlertStats:
    generated: int = 0
    persisted: int = 0
    notified: int = 0


def _utc_now(now: datetime | None = None) -> datetime:
    return now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)


def _detect_critical(session: Session, now: datetime) -> list[AlertCandidate]:
    stmt = (
        select(UnifiedReview, ReviewAnalysis)
        .join(ReviewAnalysis, ReviewAnalysis.unified_review_id == UnifiedReview.id)
        .where(ReviewAnalysis.urgency == 5)
    )
    rows = session.execute(stmt).all()

    candidates: list[AlertCandidate] = []
    for review, analysis in rows:
        event_start = review.created_at
        event_end = review.created_at + timedelta(minutes=1)
        candidates.append(
            AlertCandidate(
                severity="CRITICA",
                location_id=review.location_id,
                message=f"Urgency 5 review detected (review_id={review.id}). Immediate action required.",
                rule_code=f"CRITICA_URGENCY_5_{review.id}",
                window_start=event_start,
                window_end=event_end,
            )
        )
    return candidates


def _detect_high(session: Session, now: datetime) -> list[AlertCandidate]:
    window_end = now.replace(minute=0, second=0, microsecond=0)
    since = window_end - timedelta(hours=24)
    stmt = (
        select(UnifiedReview.location_id, func.count(ReviewAnalysis.id).label("negative_count"))
        .join(ReviewAnalysis, ReviewAnalysis.unified_review_id == UnifiedReview.id)
        .where(
            and_(
                ReviewAnalysis.sentiment == "negative",
                UnifiedReview.created_at >= since,
                UnifiedReview.created_at <= now,
            )
        )
        .group_by(UnifiedReview.location_id)
        .having(func.count(ReviewAnalysis.id) >= 3)
    )

    candidates: list[AlertCandidate] = []
    for location_id, negative_count in session.execute(stmt).all():
        candidates.append(
            AlertCandidate(
                severity="ALTA",
                location_id=location_id,
                message=f"{negative_count} negative reviews in the last 24h.",
                rule_code="ALTA_NEGATIVE_24H",
                window_start=since,
                window_end=window_end,
            )
        )
    return candidates


def _detect_medium(session: Session, now: datetime) -> list[AlertCandidate]:
    window_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = window_end - timedelta(days=7)
    stmt = (
        select(UnifiedReview.location_id, func.avg(UnifiedReview.rating).label("avg_rating"))
        .where(and_(UnifiedReview.created_at >= since, UnifiedReview.created_at <= now))
        .group_by(UnifiedReview.location_id)
        .having(func.avg(UnifiedReview.rating) < 3.5)
    )

    candidates: list[AlertCandidate] = []
    for location_id, avg_rating in session.execute(stmt).all():
        avg_rating_float = float(avg_rating)
        candidates.append(
            AlertCandidate(
                severity="MEDIA",
                location_id=location_id,
                message=f"Weekly average rating is {avg_rating_float:.2f}, below threshold 3.5.",
                rule_code="MEDIA_WEEKLY_AVG_BELOW_3_5",
                window_start=since,
                window_end=window_end,
            )
        )
    return candidates


def _alert_exists(session: Session, candidate: AlertCandidate) -> bool:
    stmt = select(Alert.id).where(
        and_(
            Alert.rule_code == candidate.rule_code,
            Alert.location_id == candidate.location_id,
            Alert.window_start == candidate.window_start,
            Alert.window_end == candidate.window_end,
        )
    )
    return session.scalar(stmt) is not None


def run_alert_detection(now: datetime | None = None) -> AlertStats:
    now_utc = _utc_now(now)
    stats = AlertStats()

    with session_scope() as session:
        candidates = _detect_critical(session=session, now=now_utc)
        candidates.extend(_detect_high(session=session, now=now_utc))
        candidates.extend(_detect_medium(session=session, now=now_utc))
        stats.generated = len(candidates)

        persisted_alerts: list[Alert] = []
        for candidate in candidates:
            if _alert_exists(session=session, candidate=candidate):
                continue

            alert = Alert(
                severity=candidate.severity,
                location_id=candidate.location_id,
                message=candidate.message,
                rule_code=candidate.rule_code,
                window_start=candidate.window_start,
                window_end=candidate.window_end,
            )
            session.add(alert)
            session.flush()
            persisted_alerts.append(alert)

        stats.persisted = len(persisted_alerts)

        notify_result = notify_alert_digest(
            alerts=persisted_alerts,
            generated=stats.generated,
            persisted=stats.persisted,
            run_at=now_utc,
        )
        if notify_result.delivered_to:
            stats.notified = stats.persisted

    return stats
