"""add the user_job_state table (rating, bookmark, applied)

One mutable row per job holding the user's own rating and bookmark/applied
marks — separate from the append-only assessments history. Fresh databases
get this table from create_all(); this migration only covers databases that
predate it. Run manually with `uv run alembic upgrade head`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_job_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("bookmarked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_user_job_state_job_id"),
    )


def downgrade() -> None:
    op.drop_table("user_job_state")
