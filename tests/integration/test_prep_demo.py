from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

import src.scripts.prep_demo as prep_demo
from src.analysis.llm_analyzer import AnalysisStats
from src.alerts.detector import AlertStats
from src.core.db import session_scope
from src.db.models import DeadLetterEvent, ReviewAnalysis, UnifiedReview
from src.reports.weekly_report import ReportStats


def test_prep_demo_backfills_and_cleans_dead_letters(sqlite_test_db, monkeypatch) -> None:
    now = datetime(2026, 4, 14, 6, 0, tzinfo=timezone.utc)
    session = Session(bind=sqlite_test_db)
    session.add_all(
        [
            UnifiedReview(
                source="api",
                source_review_id="a-1",
                location_id=1,
                rating=3,
                text="ok",
                author="u1",
                created_at=now,
                ingested_at=now,
            ),
            UnifiedReview(
                source="api",
                source_review_id="a-2",
                location_id=1,
                rating=2,
                text="bad",
                author="u2",
                created_at=now,
                ingested_at=now,
            ),
            UnifiedReview(
                source="survey",
                source_review_id="9",
                location_id=2,
                rating=4,
                text="great",
                author="u3",
                created_at=now,
                ingested_at=now,
            ),
            DeadLetterEvent(
                stage="analysis",
                source="api",
                payload={"x": 1},
                error="old error",
                created_at=now,
            ),
        ]
    )
    session.commit()
    session.close()

    def fake_analyze(limit: int) -> AnalysisStats:
        with session_scope() as s:
            pending_all = s.scalars(
                select(UnifiedReview)
                .outerjoin(ReviewAnalysis, ReviewAnalysis.unified_review_id == UnifiedReview.id)
                .where(ReviewAnalysis.id.is_(None))
                .order_by(UnifiedReview.id.asc())
            ).all()
            process_batch = pending_all[:limit]
            for review in process_batch:
                s.add(
                    ReviewAnalysis(
                        unified_review_id=review.id,
                        sentiment="neutral",
                        categories=["otro"],
                        summary="Resumen de prueba",
                        urgency=2,
                        created_at=now,
                    )
                )

        return AnalysisStats(
            pending=len(pending_all),
            analyzed=len(process_batch),
            stored=len(process_batch),
            dead_letters=0,
            errors=[],
        )

    monkeypatch.setattr(prep_demo, "analyze_pending_reviews", fake_analyze)
    monkeypatch.setattr(prep_demo, "run_alert_detection", lambda: AlertStats(generated=0, persisted=0, notified=0))
    monkeypatch.setattr(
        prep_demo,
        "generate_weekly_report",
        lambda: ReportStats(html_path="docs/weekly_report.html", pdf_path="docs/weekly_report.pdf"),
    )

    stats = prep_demo.run_prep_demo(batch_size=2, max_batches=10, clean_dead_letters=True)

    assert stats.final_pending_analysis == 0
    assert stats.dead_letters_before == 1
    assert stats.dead_letters_archived == 1
    assert stats.dead_letters_after == 0

    snapshot_path = Path(stats.dead_letters_snapshot_path)
    assert snapshot_path.exists()
    snapshot_content = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert len(snapshot_content) == 1

    snapshot_path.unlink(missing_ok=True)
