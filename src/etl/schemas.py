from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ApiReviewPayload(BaseModel):
    review_id: str
    location_id: int = Field(ge=1, le=15)
    rating: int = Field(ge=1, le=5)
    text: str
    author: str | None
    created_at: datetime

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text cannot be empty")
        return cleaned


class SurveyPayload(BaseModel):
    id: int
    location_id: int = Field(ge=1, le=15)
    rating: int = Field(ge=1, le=5)
    comments: str
    created_at: datetime
    customer_email: str | None

    @field_validator("comments")
    @classmethod
    def validate_comments(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("comments cannot be empty")
        return cleaned


class UnifiedReviewInput(BaseModel):
    source: Literal["api", "survey"]
    source_review_id: str
    location_id: int = Field(ge=1, le=15)
    rating: int = Field(ge=1, le=5)
    text: str
    author: str | None
    created_at: datetime
