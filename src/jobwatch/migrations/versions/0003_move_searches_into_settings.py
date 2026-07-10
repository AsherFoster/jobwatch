"""move searches from config.toml into the settings table

Searches are now read from the "searches" settings row (a JSON list, see
searches.py) instead of config.toml. This copies them out of an existing
config.toml so a deployed instance keeps scraping; it's a no-op if the row
already exists or there's no config.toml with searches.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-10 00:00:00.000000

"""

import json
import os
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

settings = sa.table(
    "settings",
    sa.column("key", sa.Text),
    sa.column("value", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.select(settings.c.key).where(settings.c.key == "searches")).first():
        return

    path = Path(os.environ.get("JOBWATCH_CONFIG") or "config.toml")
    if not path.exists():
        return
    searches = tomllib.loads(path.read_text()).get("searches")
    if not searches:
        return

    bind.execute(
        settings.insert().values(
            key="searches", value=json.dumps(searches), updated_at=datetime.now(UTC)
        )
    )


def downgrade() -> None:
    op.get_bind().execute(sa.delete(settings).where(settings.c.key == "searches"))
