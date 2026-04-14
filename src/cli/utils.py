from __future__ import annotations

import argparse
from datetime import date, datetime


def parse_bool_arg(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("Expected boolean value: true/false")


def parse_optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def parse_optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None

