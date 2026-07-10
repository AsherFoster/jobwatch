from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from jobwatch.config import Config, SearchConfig
from jobwatch.models import Base


@pytest.fixture(scope="session", name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as conn:
        Base.metadata.create_all(conn)

    yield engine

    engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    """Each test runs inside a SAVEPOINT nested within an outer, never-committed
    transaction. ORM-level commit/rollback ends the SAVEPOINT, so a listener restarts
    one immediately after - this isolates every test's changes without recreating the
    schema per test."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()
