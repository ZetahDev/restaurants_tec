from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import src.analysis.llm_analyzer as llm_analyzer
from src.analysis.schemas import ReviewAnalysisOutput
from src.alerts.detector import run_alert_detection
from src.core.config import get_settings
from src.core.db import session_scope
from src.db.models import ReviewAnalysis, UnifiedReview
from src.etl.pipeline import run_etl
from src.reports.weekly_report import generate_weekly_report
from src.scripts.seed import seed_customer_surveys


def test_full_pipeline_with_mocked_llm(sqlite_test_db, monkeypatch, tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("REPORT_HTML_PATH", str(tmp_path / "report.html"))
    monkeypatch.setenv("REPORT_PDF_PATH", str(tmp_path / "report.pdf"))
    get_settings.cache_clear()

    with session_scope() as session:
        seed_customer_surveys(session=session, total=220)

    def fake_fetch_api_reviews(api_base_url, location_ids, since, timeout_seconds=20.0):
        rows: list[dict] = []
        for location_id in location_ids:
            rows.append(
                {
                    "review_id": f"fake-api-{location_id}-1",
                    "location_id": int(location_id),
                    "rating": 2 if location_id % 2 == 0 else 4,
                    "text": "Servicio lento y cafe tibio." if location_id % 2 == 0 else "Muy buen servicio.",
                    "author": "bot",
                    "created_at": (now - timedelta(hours=2)).isoformat(),
                }
            )
        return rows

    monkeypatch.setattr("src.etl.pipeline.fetch_api_reviews", fake_fetch_api_reviews)

    def fake_request_analysis(client, model, review_text, rating):
        is_negative = rating <= 2 or "lento" in review_text.lower()
        output = ReviewAnalysisOutput(
            sentiment="negative" if is_negative else "positive",
            categories=["servicio"] if is_negative else ["producto"],
            summary="Atencion deficiente y experiencia negativa." if is_negative else "Experiencia positiva general.",
            urgency=4 if is_negative else 1,
        )
        return output, {
            "model": "gpt-4o-mini-mock",
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
        }

    monkeypatch.setattr(llm_analyzer, "_request_analysis", fake_request_analysis)

    etl_stats = run_etl()
    analyze_stats = llm_analyzer.analyze_pending_reviews(limit=500)
    alert_stats = run_alert_detection(now=now)
    report_stats = generate_weekly_report()

    with session_scope() as session:
        unified_count = session.query(UnifiedReview).count()
        analysis_count = session.query(ReviewAnalysis).count()

    assert etl_stats.loaded > 0
    assert analyze_stats.pending > 0
    assert analyze_stats.stored > 0
    assert unified_count > 0
    assert analysis_count > 0
    assert alert_stats.generated >= alert_stats.persisted
    assert Path(report_stats.html_path).exists()
    assert Path(report_stats.pdf_path).exists()

