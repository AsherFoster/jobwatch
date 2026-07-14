"""rename_unique_constraints_to_default_names

Revision ID: 0716795b7fd1
Revises: 289481da817e
Create Date: 2026-07-14 17:38:37.802656

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0716795b7fd1"
down_revision: str | Sequence[str] | None = "289481da817e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Constraints created with explicit uq_* names, renamed to what Postgres
# would name them by default (matching unnamed unique=True in the models).
RENAMES = [
    ("jobs", "uq_job_site_external_id", "jobs_site_external_id_key"),
    ("company_details", "uq_company_details_name", "company_details_name_key"),
    ("user_job_state", "uq_user_job_state_job_id", "user_job_state_job_id_key"),
]


def upgrade() -> None:
    """Upgrade schema."""
    for table, old, new in RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")


def downgrade() -> None:
    """Downgrade schema."""
    for table, old, new in RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {new} TO {old}")
