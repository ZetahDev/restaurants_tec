from __future__ import annotations

from datetime import datetime, timezone

from dateutil.parser import isoparse

from src.etl.schemas import ApiReviewPayload, SurveyPayload, UnifiedReviewInput


def normalize_datetime_to_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        parsed = isoparse(value)
    else:
        parsed = value

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def transform_api_review(payload: dict) -> UnifiedReviewInput:
    parsed = ApiReviewPayload.model_validate(payload)
    return UnifiedReviewInput(
        source="api",
        source_review_id=parsed.review_id,
        location_id=parsed.location_id,
        rating=parsed.rating,
        text=parsed.text.strip(),
        author=parsed.author,
        created_at=normalize_datetime_to_utc(parsed.created_at),
    )


def transform_survey_row(payload: dict) -> UnifiedReviewInput:
    parsed = SurveyPayload.model_validate(payload)
    return UnifiedReviewInput(
        source="survey",
        source_review_id=str(parsed.id),
        location_id=parsed.location_id,
        rating=parsed.rating,
        text=parsed.comments.strip(),
        author=parsed.customer_email,
        created_at=normalize_datetime_to_utc(parsed.created_at),
    )
