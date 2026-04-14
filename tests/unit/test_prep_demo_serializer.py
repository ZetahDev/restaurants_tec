from __future__ import annotations

from datetime import datetime, timezone
import json

from src.db.models import DeadLetterEvent
from src.scripts.prep_demo import _serialize_dead_letters


def test_serialize_dead_letters_produces_json_safe_structure() -> None:
    events = [
        DeadLetterEvent(
            id=7,
            stage="analysis",
            source="api",
            payload={"review_id": "x-1"},
            error="invalid response",
            created_at=datetime(2026, 4, 14, 5, 30, tzinfo=timezone.utc),
        )
    ]

    serialized = _serialize_dead_letters(events)
    assert serialized[0]["id"] == 7
    assert serialized[0]["created_at"] == "2026-04-14T05:30:00+00:00"
    assert json.loads(json.dumps(serialized)) == serialized
