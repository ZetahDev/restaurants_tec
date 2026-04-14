from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random


REVIEW_TEXTS = [
    "Amazing espresso and super quick service.",
    "The place was noisy and the wait was long.",
    "Good flavor but the coffee arrived cold.",
    "Loved the environment and friendly team.",
    "The product quality dropped since my last visit.",
    "Great pastries, average coffee.",
    "The counter area was not clean.",
    "Fantastic barista recommendations.",
    "Too expensive for what you get.",
    "Solid experience overall.",
]

AUTHORS = ["Laura", "Carlos", "Nina", "Jose", "Maya", None]


def generate_reviews(location_id: int, since: datetime) -> list[dict[str, str | int | None]]:
    rng = random.Random(location_id)
    now_utc = datetime.now(timezone.utc)

    reviews: list[dict[str, str | int | None]] = []
    for i in range(32):
        created_at = now_utc - timedelta(hours=i * 8)
        rating = rng.randint(1, 5)
        review_id = f"api-{location_id:02d}-{i:03d}"

        review = {
            "review_id": review_id,
            "location_id": location_id,
            "rating": rating,
            "text": rng.choice(REVIEW_TEXTS),
            "author": rng.choice(AUTHORS),
            "created_at": created_at.isoformat(),
        }
        reviews.append(review)

        # Deliberate duplicate rows for ETL idempotency checks.
        if i % 9 == 0:
            duplicate = dict(review)
            duplicate["created_at"] = (created_at + timedelta(minutes=2)).isoformat()
            reviews.append(duplicate)

    return [review for review in reviews if datetime.fromisoformat(str(review["created_at"])) >= since]
