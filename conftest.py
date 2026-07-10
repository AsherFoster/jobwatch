from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobwatch.models import Base


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    # StaticPool + check_same_thread=False so the TestClient's worker threads
    # see the same in-memory database as the test's own session.
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session
