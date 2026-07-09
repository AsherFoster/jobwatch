from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from jobwatch.config import Config, CriteriaConfig, SearchConfig
from jobwatch.db import make_engine, make_session_factory


@pytest.fixture
def config() -> Config:
    return Config(
        database_url="sqlite:///:memory:",
        searches=[SearchConfig(name="test", search_term="engineer", location="Denmark")],
        criteria=CriteriaConfig(text="Positives: python. Negatives: data analysis."),
    )


@pytest.fixture
def session() -> Iterator[Session]:
    factory = make_session_factory(make_engine("sqlite:///:memory:"))
    with factory() as s:
        yield s
