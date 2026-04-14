from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random

from sqlalchemy import delete
from sqlalchemy.orm import Session

from src.db.models import CustomerSurvey


POSITIVE_COMMENTS = [
    "Excellent coffee and very friendly staff.",
    "Great experience, fast service and tasty products.",
    "The ambiance is great, I will definitely come back.",
    "Loved the cappuccino and the pastry quality.",
]

NEUTRAL_COMMENTS = [
    "It was okay, average waiting time.",
    "Nothing special, but acceptable quality.",
    "Service was fine, prices a bit high.",
    "Normal experience, place was crowded.",
]

NEGATIVE_COMMENTS = [
    "The coffee was cold and the wait was too long.",
    "Very bad service, the order came wrong.",
    "The place was dirty and noisy.",
    "Too expensive for the quality received.",
    "Staff was rude and unhelpful.",
]


@dataclass(frozen=True)
class SeedStats:
    inserted: int


def _pick_comment(rating: int, rng: random.Random) -> str:
    if rating >= 4:
        return rng.choice(POSITIVE_COMMENTS)
    if rating == 3:
        return rng.choice(NEUTRAL_COMMENTS)
    return rng.choice(NEGATIVE_COMMENTS)


def _pick_email(index: int, rng: random.Random) -> str | None:
    if index % 4 == 0:
        return None
    return f"customer{index:03d}@example.com"


def seed_customer_surveys(session: Session, total: int = 220) -> SeedStats:
    rng = random.Random(42)
    now_utc = datetime.now(timezone.utc)

    session.execute(delete(CustomerSurvey))
    records: list[CustomerSurvey] = []

    for i in range(total):
        location_id = (i % 15) + 1
        rating = rng.choices(population=[1, 2, 3, 4, 5], weights=[10, 15, 25, 30, 20], k=1)[0]
        created_at = now_utc - timedelta(days=rng.randint(0, 30), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        records.append(
            CustomerSurvey(
                location_id=location_id,
                rating=rating,
                comments=_pick_comment(rating, rng),
                created_at=created_at,
                customer_email=_pick_email(i, rng),
            )
        )

    # Force alert-friendly cases in the latest 24h for later validation.
    records.extend(
        [
            CustomerSurvey(
                location_id=4,
                rating=1,
                comments="Critical complaint: dirty tables and rude service.",
                created_at=now_utc - timedelta(hours=2),
                customer_email="urgent1@example.com",
            ),
            CustomerSurvey(
                location_id=4,
                rating=1,
                comments="Another bad experience, wrong order and no apology.",
                created_at=now_utc - timedelta(hours=4),
                customer_email="urgent2@example.com",
            ),
            CustomerSurvey(
                location_id=4,
                rating=2,
                comments="Long wait and poor product quality.",
                created_at=now_utc - timedelta(hours=6),
                customer_email="urgent3@example.com",
            ),
        ]
    )

    session.add_all(records)
    session.flush()
    return SeedStats(inserted=len(records))
