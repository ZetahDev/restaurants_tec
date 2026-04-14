from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Query

from src.api.data import generate_reviews

app = FastAPI(title="FeedbackIQ Dummy API")


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "FeedbackIQ Dummy API",
        "description": "Fuente A para reseñas de BrewMaster",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "endpoints": [
            "GET /health",
            "GET /api/reviews?location_id={id}&since={iso8601}",
        ],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/reviews")
def get_reviews(
    location_id: int = Query(..., ge=1, le=15),
    since: datetime = Query(..., description="ISO-8601 UTC timestamp"),
) -> list[dict[str, Any]]:
    if since.tzinfo is None:
        since_dt = since.replace(tzinfo=timezone.utc)
    else:
        since_dt = since.astimezone(timezone.utc)

    return generate_reviews(location_id=location_id, since=since_dt)
