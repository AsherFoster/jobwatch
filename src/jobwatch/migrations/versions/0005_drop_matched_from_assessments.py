"""drop matched from assessments

Whether a job matched is now derived from its score (>= 4 stars), so the
stored boolean was redundant — and could disagree with the score for rows
that predate the star scale. Run manually with
`uv run alembic upgrade head` against your deployed DB.

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
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.drop_column("matched")


def downgrade() -> None:
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.add_column(
            sa.Column("matched", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
    op.execute("UPDATE assessments SET matched = (score >= 4)")
