from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

import httpx
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import get_settings
from src.db.models import Alert


@dataclass
class NotificationResult:
    delivered_to: str
    detail: str


class AlertDigestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=30, max_length=420)


def _alert_payload(alert: Alert) -> dict[str, str | int]:
    return {
        "id": alert.id,
        "severity": alert.severity,
        "location_id": alert.location_id,
        "rule_code": alert.rule_code,
        "message": alert.message,
        "created_at": alert.created_at.isoformat() if isinstance(alert.created_at, datetime) else str(alert.created_at),
    }


def _fallback_summary(
    alerts: list[Alert],
    generated: int,
    persisted: int,
    severity_counts: Counter,
) -> str:
    top = Counter(alert.location_id for alert in alerts).most_common(3)
    top_txt = ", ".join(f"loc {location} ({count})" for location, count in top) if top else "sin concentración"
    return (
        f"Se detectaron {generated} alertas y se registraron {persisted} nuevas. "
        f"Distribución nuevas: CRITICA={severity_counts.get('CRITICA', 0)}, "
        f"ALTA={severity_counts.get('ALTA', 0)}, MEDIA={severity_counts.get('MEDIA', 0)}. "
        f"Mayor impacto en {top_txt}."
    )


def _ai_summary(
    alerts: list[Alert],
    generated: int,
    persisted: int,
    severity_counts: Counter,
) -> str:
    settings = get_settings()
    fallback = _fallback_summary(alerts=alerts, generated=generated, persisted=persisted, severity_counts=severity_counts)

    if not settings.openai_api_key:
        return fallback

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        payload = {
            "generated": generated,
            "persisted": persisted,
            "severity_counts": {
                "CRITICA": severity_counts.get("CRITICA", 0),
                "ALTA": severity_counts.get("ALTA", 0),
                "MEDIA": severity_counts.get("MEDIA", 0),
            },
            "alerts": [_alert_payload(alert) for alert in alerts[:20]],
        }

        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un analista operativo. Devuelve un JSON valido con una sola clave `summary`. "
                        "La respuesta debe ser 2 a 4 lineas en español, accionable, y sin markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Genera el resumen ejecutivo del lote con estos datos: {json.dumps(payload, ensure_ascii=False)}",
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "alert_digest_summary",
                    "strict": True,
                    "schema": AlertDigestSummary.model_json_schema(),
                },
            },
        )

        content = response.choices[0].message.content or "{}"
        parsed = AlertDigestSummary.model_validate(json.loads(content))
        return parsed.summary
    except Exception:
        return fallback


def _format_alert_lines(alerts: list[Alert], severity: str) -> list[str]:
    selected = [alert for alert in alerts if alert.severity == severity]
    if not selected:
        return ["- Sin alertas nuevas."]

    lines: list[str] = []
    for alert in selected[:10]:
        message = alert.message.strip()
        if len(message) > 110:
            message = f"{message[:107]}..."
        lines.append(f"- loc {alert.location_id} | {alert.rule_code}: {message}")
    return lines


def build_alert_digest(
    alerts: list[Alert],
    generated: int,
    persisted: int,
    run_at: datetime,
) -> dict:
    severity_counts = Counter(alert.severity for alert in alerts)
    location_counts = Counter(alert.location_id for alert in alerts)
    top_locations = ", ".join(
        f"loc {location} ({count})" for location, count in location_counts.most_common(3)
    ) or "sin concentración"

    ai_summary = _ai_summary(
        alerts=alerts,
        generated=generated,
        persisted=persisted,
        severity_counts=severity_counts,
    )

    actions: list[str] = []
    if severity_counts.get("CRITICA", 0):
        actions.append("Escalar CRITICAS al gerente de turno en menos de 15 minutos.")
    if severity_counts.get("ALTA", 0):
        actions.append("Asignar revisión operativa hoy para locales con ALTA recurrencia.")
    if severity_counts.get("MEDIA", 0):
        actions.append("Revisar plan semanal de calidad para locales con rating bajo.")
    if not actions:
        actions.append("Sin acciones inmediatas; mantener monitoreo en siguiente corrida.")

    sections = [
        "*BrewMaster | FeedbackIQ Digest de Alertas*",
        f"Fecha: {run_at.isoformat()}",
        "",
        "*Resumen del lote*",
        f"- Detectadas en evaluación: {generated}",
        f"- Nuevas guardadas/notificables: {persisted}",
        f"- Distribución nuevas: CRITICA={severity_counts.get('CRITICA', 0)}, ALTA={severity_counts.get('ALTA', 0)}, MEDIA={severity_counts.get('MEDIA', 0)}",
        f"- Top locales afectados: {top_locations}",
        "",
        "*Resumen IA*",
        ai_summary,
        "",
        "*Alertas CRITICA*",
        *_format_alert_lines(alerts, "CRITICA"),
        "",
        "*Alertas ALTA*",
        *_format_alert_lines(alerts, "ALTA"),
        "",
        "*Alertas MEDIA*",
        *_format_alert_lines(alerts, "MEDIA"),
        "",
        "*Acciones recomendadas*",
        *(f"- {action}" for action in actions),
    ]

    text = "\n".join(sections)
    return {
        "text": text,
        "meta": {
            "generated": generated,
            "persisted": persisted,
            "severity_counts": dict(severity_counts),
            "alerts": [_alert_payload(alert) for alert in alerts],
        },
    }


def _write_fallback(payload: dict) -> NotificationResult:
    fallback_file = Path("artifacts/alerts_webhook_fallback.jsonl")
    fallback_file.parent.mkdir(parents=True, exist_ok=True)
    with fallback_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return NotificationResult(delivered_to="json_fallback", detail=str(fallback_file))


def notify_alert_digest(
    alerts: list[Alert],
    generated: int,
    persisted: int,
    run_at: datetime,
) -> NotificationResult:
    settings = get_settings()
    digest = build_alert_digest(
        alerts=alerts,
        generated=generated,
        persisted=persisted,
        run_at=run_at,
    )

    if not settings.slack_webhook_url:
        return _write_fallback(digest)

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(settings.slack_webhook_url, json={"text": digest["text"]})
            response.raise_for_status()
        return NotificationResult(delivered_to="slack", detail="digest_sent")
    except Exception as exc:
        digest["meta"]["notification_error"] = str(exc)
        return _write_fallback(digest)
