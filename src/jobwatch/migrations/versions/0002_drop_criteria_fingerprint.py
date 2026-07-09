"""drop criteria_fingerprint from assessments

Staleness is no longer detected by comparing a (criteria, model) fingerprint
against a stored one — an assessment's `invalidated_at` already says whether
it's the current verdict, so the fingerprint was redundant. Only needed for
databases that predate this change; run manually with
`uv run alembic upgrade head` against your deployed DB.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.drop_index("ix_assessments_fingerprint")
        batch_op.drop_column("criteria_fingerprint")


def downgrade() -> None:
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.add_column(sa.Column("criteria_fingerprint", sa.Text(), nullable=True))
        batch_op.create_index("ix_assessments_fingerprint", ["criteria_fingerprint"])
