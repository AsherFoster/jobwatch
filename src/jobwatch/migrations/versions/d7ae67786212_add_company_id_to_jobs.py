"""add_company_id_to_jobs

Revision ID: d7ae67786212
Revises: f75ac168dbd0
Create Date: 2026-07-18 12:50:10.744728

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7ae67786212"
down_revision: str | Sequence[str] | None = "f75ac168dbd0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "company_details", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("jobs", sa.Column("company_id", sa.Integer(), nullable=True))

    conn = op.get_bind()
    # Backfill: one CompanyDetails row per distinct (case-insensitive) job
    # company name, reusing an existing row if its name already matches.
    conn.execute(
        sa.text(
            """
            INSERT INTO company_details (name, description, created_at)
            SELECT DISTINCT ON (lower(company)) company, '', now()
            FROM jobs
            WHERE NOT EXISTS (
                SELECT 1 FROM company_details cd WHERE cd.name ILIKE jobs.company
            )
            ORDER BY lower(company), company
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE jobs
            SET company_id = company_details.id
            FROM company_details
            WHERE company_details.name ILIKE jobs.company
            """
        )
    )

    op.alter_column("jobs", "company_id", nullable=False)
    op.create_foreign_key("fk_jobs_company_id", "jobs", "company_details", ["company_id"], ["id"])
    op.drop_column("jobs", "company")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("jobs", sa.Column("company", sa.Text(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE jobs
            SET company = company_details.name
            FROM company_details
            WHERE company_details.id = jobs.company_id
            """
        )
    )

    op.alter_column("jobs", "company", nullable=False)
    op.drop_constraint("fk_jobs_company_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "company_id")
    op.drop_column("company_details", "generated_at")
