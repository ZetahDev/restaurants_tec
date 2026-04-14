from __future__ import annotations

from datetime import timezone

from src.etl.transformers import normalize_datetime_to_utc, transform_api_review, transform_survey_row


def test_normalize_datetime_to_utc_from_offset_string() -> None:
    normalized = normalize_datetime_to_utc("2026-04-13T15:00:00-05:00")
    assert normalized.tzinfo == timezone.utc
    assert normalized.isoformat() == "2026-04-13T20:00:00+00:00"


def test_transform_api_and_survey_to_unified_schema() -> None:
    api_review = {
        "review_id": "api-1",
        "location_id": 1,
        "rating": 5,
        "text": "  Great service!  ",
        "author": "Ana",
        "created_at": "2026-04-13T18:00:00+00:00",
    }
    survey_row = {
        "id": 10,
        "location_id": 2,
        "rating": 3,
        "comments": "  Average experience. ",
        "created_at": "2026-04-13T12:00:00-03:00",
        "customer_email": "user@example.com",
    }

    unified_api = transform_api_review(api_review)
    unified_survey = transform_survey_row(survey_row)

    assert unified_api.source == "api"
    assert unified_api.source_review_id == "api-1"
    assert unified_api.text == "Great service!"

    assert unified_survey.source == "survey"
    assert unified_survey.source_review_id == "10"
    assert unified_survey.author == "user@example.com"
    assert unified_survey.created_at.isoformat() == "2026-04-13T15:00:00+00:00"
