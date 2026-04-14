from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import get_settings
from src.core.db import get_engine, get_session_factory
from src.db.models import Base


@pytest.fixture
def sqlite_test_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "test_feedbackiq.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    engine = get_engine()
    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
