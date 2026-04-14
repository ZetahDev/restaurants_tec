from __future__ import annotations

from datetime import datetime
from typing import Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import CustomerSurvey


def fetch_api_reviews(
    api_base_url: str,
    location_ids: Iterable[int],
    since: datetime,
    timeout_seconds: float = 20.0,
) -> list[dict]:
    all_reviews: list[dict] = []
    endpoint = f"{api_base_url.rstrip('/')}/api/reviews"

    with httpx.Client(timeout=timeout_seconds) as client:
        for location_id in location_ids:
            response = client.get(
                endpoint,
                params={"location_id": location_id, "since": since.isoformat()},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("API payload must be a list")
            all_reviews.extend(payload)

    return all_reviews


def fetch_recent_surveys(session: Session, since: datetime) -> list[dict]:
    stmt = select(CustomerSurvey).where(CustomerSurvey.created_at >= since)
    rows = session.scalars(stmt).all()

    return [
        {
            "id": row.id,
            "location_id": row.location_id,
            "rating": row.rating,
            "comments": row.comments,
            "created_at": row.created_at,
            "customer_email": row.customer_email,
        }
        for row in rows
    ]
