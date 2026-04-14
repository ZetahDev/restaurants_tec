from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import delete, func, select

from src.alerts.detector import AlertStats, run_alert_detection
from src.analysis.llm_analyzer import AnalysisStats, analyze_pending_reviews
from src.core.db import session_scope
from src.db.models import Alert, DeadLetterEvent, ReviewAnalysis, UnifiedReview
from src.reports.weekly_report import ReportStats, generate_weekly_report


@dataclass
class PrepDemoStats:
    batches_run: int
    analyzed_total: int
    final_pending_analysis: int
    dead_letters_before: int
    dead_letters_archived: int
    dead_letters_after: int
    dead_letters_snapshot_path: str
    alerts_generated: int
    alerts_persisted: int
    alerts_notified: int
    report_html_path: str
    report_pdf_path: str
    unified_reviews: int
    review_analysis: int
    alerts_total: int


def _query_counts() -> dict[str, int]:
    with session_scope() as session:
        unified_reviews = session.scalar(select(func.count(UnifiedReview.id))) or 0
        review_analysis = session.scalar(select(func.count(ReviewAnalysis.id))) or 0
        alerts_total = session.scalar(select(func.count(Alert.id))) or 0
        pending_analysis = session.scalar(
            select(func.count(UnifiedReview.id))
            .outerjoin(ReviewAnalysis, ReviewAnalysis.unified_review_id == UnifiedReview.id)
            .where(ReviewAnalysis.id.is_(None))
        ) or 0
        dead_letters = session.scalar(select(func.count(DeadLetterEvent.id))) or 0

    return {
        "unified_reviews": int(unified_reviews),
        "review_analysis": int(review_analysis),
        "alerts_total": int(alerts_total),
        "pending_analysis": int(pending_analysis),
        "dead_letters": int(dead_letters),
    }


def _serialize_dead_letters(events: list[DeadLetterEvent]) -> list[dict]:
    serialized: list[dict] = []
    for event in events:
        serialized.append(
            {
                "id": event.id,
                "stage": event.stage,
                "source": event.source,
                "payload": event.payload,
                "error": event.error,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
        )
    return serialized


def _archive_dead_letters() -> tuple[str, int]:
    with session_scope() as session:
        events = session.scalars(select(DeadLetterEvent).order_by(DeadLetterEvent.id.asc())).all()
        serialized = _serialize_dead_letters(events)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = Path(f"artifacts/dead_letters_snapshot_{timestamp}.json")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(serialized, ensure_ascii=True, indent=2), encoding="utf-8")
    return str(snapshot_path), len(serialized)


def _clear_dead_letters() -> int:
    with session_scope() as session:
        deleted = session.execute(delete(DeadLetterEvent)).rowcount or 0
    return int(deleted)


def _run_backfill(batch_size: int, max_batches: int) -> tuple[int, int]:
    analyzed_total = 0
    batches_run = 0

    for _ in range(max_batches):
        stats: AnalysisStats = analyze_pending_reviews(limit=batch_size)
        batches_run += 1
        analyzed_total += stats.analyzed

        if stats.pending == 0:
            break
        if stats.analyzed == 0:
            break

    return batches_run, analyzed_total


def run_prep_demo(
    batch_size: int = 100,
    max_batches: int = 20,
    clean_dead_letters: bool = True,
) -> PrepDemoStats:
    dead_letters_before = _query_counts()["dead_letters"]

    batches_run, analyzed_total = _run_backfill(batch_size=batch_size, max_batches=max_batches)

    snapshot_path, archived_count = _archive_dead_letters()
    if clean_dead_letters:
        _clear_dead_letters()

    dead_letters_after = _query_counts()["dead_letters"]
    alert_stats: AlertStats = run_alert_detection()
    report_stats: ReportStats = generate_weekly_report()
    final_counts = _query_counts()

    return PrepDemoStats(
        batches_run=batches_run,
        analyzed_total=analyzed_total,
        final_pending_analysis=final_counts["pending_analysis"],
        dead_letters_before=dead_letters_before,
        dead_letters_archived=archived_count,
        dead_letters_after=dead_letters_after,
        dead_letters_snapshot_path=snapshot_path,
        alerts_generated=alert_stats.generated,
        alerts_persisted=alert_stats.persisted,
        alerts_notified=alert_stats.notified,
        report_html_path=report_stats.html_path,
        report_pdf_path=report_stats.pdf_path,
        unified_reviews=final_counts["unified_reviews"],
        review_analysis=final_counts["review_analysis"],
        alerts_total=final_counts["alerts_total"],
    )


def stats_to_json(stats: PrepDemoStats) -> str:
    return json.dumps(asdict(stats), ensure_ascii=True, indent=2)
