from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

os.environ.setdefault("ENVIRONMENT", "test")
assert os.environ.get("ENVIRONMENT") == "test"

# ruff: noqa: E402
from jobwatch.config import config
from jobwatch.models import Base


def _create_test_database_if_missing(database_url: str) -> None:
    url = make_url(database_url)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", name="engine")
def engine_fixture():
    """
    Real Postgres engine, schema created once per test run.

    Tests should not use this unless absolutely necessary.
    """

    _create_test_database_if_missing(config.database_url)
    engine = create_engine(config.database_url)
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)

        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))

        Base.metadata.create_all(conn)

    yield engine

    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
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
