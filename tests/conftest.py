from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobwatch.config import Config, SearchConfig
from jobwatch.models import Base


@pytest.fixture
def config() -> Config:
    return Config(
        database_url="sqlite:///:memory:",
        searches=[SearchConfig(name="test", search_term="engineer", location="Denmark")],
    )


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    session_maker = sessionmaker(engine)

    Base.metadata.create_all(engine)

    with session_maker() as session:
        yield session
