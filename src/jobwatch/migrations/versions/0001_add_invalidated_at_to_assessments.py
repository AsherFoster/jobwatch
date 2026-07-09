"""add invalidated_at to assessments

Reevaluating a job now invalidates its previous verdict instead of deleting
it, so `assessments` needs to allow more than one row per (job, criteria
fingerprint) over time. The old unconditional unique constraint is replaced
by a partial unique index that only applies to the still-active row.

Only needed for databases that predate this change — run manually with
`uv run alembic upgrade head` against your deployed DB. A brand new database
already gets this schema from `Base.metadata.create_all()` on first run, so
there's no baseline migration here recreating table history that create_all()
already handles.

Revision ID: 0001
Revises:
Create Date: 2026-07-09 16:14:46.865792

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.add_column(sa.Column("invalidated_at", sa.DateTime(timezone=True)))
        batch_op.drop_constraint("uq_assessment_job_criteria", type_="unique")

    op.create_index(
        "uq_assessment_job_active",
        "assessments",
        ["job_id"],
        unique=True,
        sqlite_where=sa.text("invalidated_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_assessment_job_active", table_name="assessments")
    with op.batch_alter_table("assessments") as batch_op:
        batch_op.create_unique_constraint(
            "uq_assessment_job_criteria", ["job_id", "criteria_fingerprint"]
        )
        batch_op.drop_column("invalidated_at")
