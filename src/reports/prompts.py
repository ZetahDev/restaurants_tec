from __future__ import annotations

from typing import Any


REPORT_SUMMARY_SYSTEM_PROMPT = "Eres un analista senior de operaciones."


def build_report_summary_user_prompt(metrics_payload: dict[str, Any]) -> str:
    return (
        "Escribe un resumen ejecutivo en un párrafo (max 450 caracteres) para gerencia. "
        "Usa un tono profesional y accionable en español.\n"
        f"Métricas: {metrics_payload}"
    )

