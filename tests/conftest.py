from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from jobwatch.config import Config, SearchConfig
from jobwatch.criteria import set_criteria_text
from jobwatch.db import make_engine, make_session_factory


@pytest.fixture
def config() -> Config:
    return Config(
        database_url="sqlite:///:memory:",
        searches=[SearchConfig(name="test", search_term="engineer", location="Denmark")],
    )


@pytest.fixture
def session() -> Iterator[Session]:
    factory = make_session_factory(make_engine("sqlite:///:memory:"))
    with factory() as s:
        set_criteria_text(s, "Positives: python. Negatives: data analysis.")
        yield s
