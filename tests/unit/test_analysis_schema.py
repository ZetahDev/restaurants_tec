from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.analysis.schemas import ReviewAnalysisOutput


def test_review_analysis_schema_accepts_valid_payload() -> None:
    payload = {
        "sentiment": "negative",
        "categories": ["servicio", "precio"],
        "summary": "Servicio lento y precio alto para la calidad.",
        "urgency": 4,
    }
    validated = ReviewAnalysisOutput.model_validate(payload)
    assert validated.sentiment == "negative"


def test_review_analysis_schema_rejects_invalid_category() -> None:
    payload = {
        "sentiment": "neutral",
        "categories": ["delivery"],
        "summary": "Comentario de prueba.",
        "urgency": 2,
    }
    with pytest.raises(ValidationError):
        ReviewAnalysisOutput.model_validate(payload)
