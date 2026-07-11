from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobwatch.models import Base

# Test modules are imported after this file, and jobwatch.config loads its file
# at import time — config.toml (the default) is gitignored so may not exist.
# Keep conftest's own imports free of anything that pulls in jobwatch.config.
os.environ.setdefault("JOBWATCH_CONFIG", str(Path(__file__).parent / "config.test.toml"))


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
