from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_USAGE_PATH = Path("artifacts/llm_usage.jsonl")


@dataclass(frozen=True)
class LLMUsageEvent:
    created_at: str
    stage: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    unified_review_id: int
    source: str
    source_review_id: str
    location_id: int
    rating: int
    text_length: int


def write_usage_event(event: LLMUsageEvent, path: str | Path = DEFAULT_USAGE_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(event), ensure_ascii=True))  # type: ignore
        handle.write("\n")


def summarize_usage(path: str | Path = DEFAULT_USAGE_PATH, since_hours: int | None = None) -> dict[str, Any]:
    target = Path(path)
    now_utc = datetime.now(timezone.utc)
    cutoff: datetime | None = None
    if since_hours is not None:
        cutoff = now_utc - timedelta(hours=since_hours)

    if not target.exists():
        return {
            "path": str(target),
            "exists": False,
            "filtered_since_hours": since_hours,
            "events": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "avg_total_tokens_per_event": 0.0,
            "models": {},
            "window_start": None,
            "window_end": None,
            "top_token_events": [],
        }

    events: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        created_at_raw = event.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_at_raw)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            else:
                created_at = created_at.astimezone(timezone.utc)
        except Exception:
            continue

        if cutoff is not None and created_at < cutoff:  # type: ignore
            continue

        event["created_at"] = created_at.isoformat()
        events.append(event)

    total_prompt = sum(int(event.get("prompt_tokens", 0)) for event in events)
    total_completion = sum(int(event.get("completion_tokens", 0)) for event in events)
    total_tokens = sum(int(event.get("total_tokens", 0)) for event in events)
    event_count = len(events)

    models: dict[str, dict[str, int]] = {}
    for event in events:
        model = str(event.get("model", "unknown"))
        if model not in models:
            models[model] = {
                "events": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        models[model]["events"] += 1
        models[model]["prompt_tokens"] += int(event.get("prompt_tokens", 0))
        models[model]["completion_tokens"] += int(event.get("completion_tokens", 0))
        models[model]["total_tokens"] += int(event.get("total_tokens", 0))

    top_token_events = sorted(
        events,
        key=lambda item: int(item.get("total_tokens", 0)),
        reverse=True,
    )[:5]  # type: ignore

    created_at_values = [datetime.fromisoformat(event["created_at"]) for event in events]
    window_start = min(created_at_values).isoformat() if created_at_values else None
    window_end = max(created_at_values).isoformat() if created_at_values else None

    return {
        "path": str(target),
        "exists": True,
        "filtered_since_hours": since_hours,
        "events": event_count,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "avg_total_tokens_per_event": round(total_tokens / event_count, 2) if event_count else 0.0,  # type: ignore
        "models": models,
        "window_start": window_start,
        "window_end": window_end,
        "top_token_events": top_token_events,
    }

