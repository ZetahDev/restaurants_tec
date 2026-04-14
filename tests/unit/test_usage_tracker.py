from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.analysis.usage_tracker import LLMUsageEvent, summarize_usage, write_usage_event


def test_usage_tracker_writes_and_summarizes(tmp_path):
    usage_path = tmp_path / "llm_usage.jsonl"
    now = datetime.now(timezone.utc)

    write_usage_event(
        LLMUsageEvent(
            created_at=(now - timedelta(minutes=10)).isoformat(),
            stage="analysis",
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=30,
            total_tokens=130,
            unified_review_id=1,
            source="api",
            source_review_id="api-01-001",
            location_id=1,
            rating=2,
            text_length=80,
        ),
        path=usage_path,
    )

    write_usage_event(
        LLMUsageEvent(
            created_at=(now - timedelta(minutes=5)).isoformat(),
            stage="analysis",
            model="gpt-4o-mini",
            prompt_tokens=120,
            completion_tokens=25,
            total_tokens=145,
            unified_review_id=2,
            source="survey",
            source_review_id="2",
            location_id=4,
            rating=1,
            text_length=90,
        ),
        path=usage_path,
    )

    summary = summarize_usage(path=usage_path)
    assert summary["exists"] is True
    assert summary["events"] == 2
    assert summary["total_prompt_tokens"] == 220
    assert summary["total_completion_tokens"] == 55
    assert summary["total_tokens"] == 275
    assert summary["models"]["gpt-4o-mini"]["events"] == 2
    assert len(summary["top_token_events"]) == 2


def test_usage_tracker_filters_by_time_window(tmp_path):
    usage_path = tmp_path / "llm_usage.jsonl"
    now = datetime.now(timezone.utc)

    write_usage_event(
        LLMUsageEvent(
            created_at=(now - timedelta(hours=5)).isoformat(),
            stage="analysis",
            model="gpt-4o-mini",
            prompt_tokens=200,
            completion_tokens=50,
            total_tokens=250,
            unified_review_id=10,
            source="api",
            source_review_id="old",
            location_id=2,
            rating=3,
            text_length=45,
        ),
        path=usage_path,
    )

    write_usage_event(
        LLMUsageEvent(
            created_at=(now - timedelta(minutes=20)).isoformat(),
            stage="analysis",
            model="gpt-4o-mini",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            unified_review_id=11,
            source="api",
            source_review_id="new",
            location_id=3,
            rating=4,
            text_length=75,
        ),
        path=usage_path,
    )

    summary = summarize_usage(path=usage_path, since_hours=1)
    assert summary["events"] == 1
    assert summary["total_tokens"] == 75

