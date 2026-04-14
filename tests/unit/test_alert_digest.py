from __future__ import annotations

from datetime import datetime, timezone

from src.alerts.notifier import build_alert_digest
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


def test_build_alert_digest_renders_sections_and_counters(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    alerts = [
        _alert("CRITICA", 4, "CRITICA_URGENCY_5_1", "Urgencia máxima detectada."),
        _alert("ALTA", 4, "ALTA_NEGATIVE_24H", "5 negativas en 24h."),
        _alert("MEDIA", 2, "MEDIA_WEEKLY_AVG_BELOW_3_5", "Promedio por debajo de 3.5."),
    ]

    digest = build_alert_digest(
        alerts=alerts,
        generated=7,
        persisted=3,
        run_at=datetime(2026, 4, 14, 3, 0, tzinfo=timezone.utc),
    )

    text = digest["text"]
    assert "Resumen del lote" in text
    assert "Alertas CRITICA" in text
    assert "Alertas ALTA" in text
    assert "Alertas MEDIA" in text
    assert "Acciones recomendadas" in text
    assert "CRITICA=1, ALTA=1, MEDIA=1" in text


def test_build_alert_digest_falls_back_when_ai_fails(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    class BrokenOpenAI:
        def __init__(self, api_key: str):
            self.api_key = api_key

            class _Chat:
                class _Completions:
                    @staticmethod
                    def create(**kwargs):
                        raise RuntimeError("simulated openai failure")

                completions = _Completions()

            self.chat = _Chat()

    monkeypatch.setattr("src.alerts.notifier.OpenAI", BrokenOpenAI)

    digest = build_alert_digest(
        alerts=[_alert("MEDIA", 1, "MEDIA_WEEKLY_AVG_BELOW_3_5", "Promedio semanal bajo")],
        generated=2,
        persisted=1,
        run_at=datetime(2026, 4, 14, 4, 0, tzinfo=timezone.utc),
    )

    assert "Se detectaron 2 alertas" in digest["text"]
