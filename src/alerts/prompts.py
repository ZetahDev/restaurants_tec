from __future__ import annotations

import json
from typing import Any


ALERT_DIGEST_SUMMARY_SYSTEM_PROMPT = (
    "Eres un analista operativo. Devuelve un JSON valido con una sola clave `summary`. "
    "La respuesta debe ser 2 a 4 lineas en español, accionable, y sin markdown."
)


def build_alert_digest_summary_user_prompt(payload: dict[str, Any]) -> str:
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    return f"Genera el resumen ejecutivo del lote con estos datos: {serialized_payload}"

