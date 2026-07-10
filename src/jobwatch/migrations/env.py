from alembic import context

from jobwatch.config import config
from jobwatch.db import engine
from jobwatch.models import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection, emitting SQL to stdout."""
    context.configure(
        url=config.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB, reusing jobwatch's own engine setup
    (`make_engine`: sqlite pragmas, dir creation) instead of building a
    separate one from alembic.ini."""
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
