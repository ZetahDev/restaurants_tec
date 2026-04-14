from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path

import httpx

from src.core.config import get_settings
from src.db.models import Alert


@dataclass
class NotificationResult:
    delivered_to: str
    detail: str


def _alert_payload(alert: Alert) -> dict[str, str | int]:
    return {
        "id": alert.id,
        "severity": alert.severity,
        "location_id": alert.location_id,
        "rule_code": alert.rule_code,
        "message": alert.message,
        "created_at": alert.created_at.isoformat() if isinstance(alert.created_at, datetime) else str(alert.created_at),
    }


def _write_fallback(payload: dict) -> NotificationResult:
    fallback_file = Path("artifacts/alerts_webhook_fallback.jsonl")
    fallback_file.parent.mkdir(parents=True, exist_ok=True)
    with fallback_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return NotificationResult(delivered_to="json_fallback", detail=str(fallback_file))


def notify_alert(alert: Alert) -> NotificationResult:
    settings = get_settings()
    payload = _alert_payload(alert)

    if not settings.slack_webhook_url:
        return _write_fallback(payload)

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(settings.slack_webhook_url, json={"text": json.dumps(payload, ensure_ascii=False)})
            response.raise_for_status()
        return NotificationResult(delivered_to="slack", detail="webhook_sent")
    except Exception as exc:
        payload["notification_error"] = str(exc)
        return _write_fallback(payload)
