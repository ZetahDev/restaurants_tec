from __future__ import annotations

from datetime import datetime, timezone

from src.alerts.notifier import notify_alert_digest
from src.core.config import get_settings
from src.db.models import Alert


def _alert(severity: str, location: int, rule_code: str, message: str) -> Alert:
    return Alert(
        id=1,
        severity=severity,
        location_id=location,
        rule_code=rule_code,
        message=message,
        window_start=datetime(2026, 4, 14, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc),
    )


def test_notify_alert_digest_sends_extra_immediate_message_for_critical(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    sent_texts: list[str] = []

    def fake_send_slack_text(webhook_url: str, text: str) -> None:
        sent_texts.append(text)

    monkeypatch.setattr("src.alerts.notifier._send_slack_text", fake_send_slack_text)

    result = notify_alert_digest(
        alerts=[
            _alert("CRITICA", 4, "CRITICA_URGENCY_5_100", "Incidente severo en tienda."),
            _alert("MEDIA", 2, "MEDIA_WEEKLY_AVG_BELOW_3_5", "Promedio semanal bajo."),
        ],
        generated=2,
        persisted=2,
        run_at=datetime(2026, 4, 14, 3, 0, tzinfo=timezone.utc),
    )

    assert result.delivered_to == "slack"
    assert result.detail == "digest_and_critical_sent"
    assert len(sent_texts) == 2
    assert "Digest de Alertas" in sent_texts[0]
    assert "ALERTA INMEDIATA CRITICA" in sent_texts[1]


def test_notify_alert_digest_without_critical_sends_only_digest(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    sent_texts: list[str] = []

    def fake_send_slack_text(webhook_url: str, text: str) -> None:
        sent_texts.append(text)

    monkeypatch.setattr("src.alerts.notifier._send_slack_text", fake_send_slack_text)

    result = notify_alert_digest(
        alerts=[_alert("MEDIA", 2, "MEDIA_WEEKLY_AVG_BELOW_3_5", "Promedio semanal bajo.")],
        generated=1,
        persisted=1,
        run_at=datetime(2026, 4, 14, 3, 0, tzinfo=timezone.utc),
    )

    assert result.delivered_to == "slack"
    assert result.detail == "digest_sent"
    assert len(sent_texts) == 1

