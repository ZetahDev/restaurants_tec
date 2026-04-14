from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sentiment = Literal["positive", "negative", "neutral"]
Category = Literal["producto", "servicio", "ambiente", "precio", "limpieza", "otro"]


class ReviewAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentiment: Sentiment
    categories: list[Category] = Field(min_length=1)
    summary: str = Field(max_length=100)
    urgency: int = Field(ge=1, le=5)

    @field_validator("summary")
    @classmethod
    def summary_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("summary cannot be empty")
        return cleaned
