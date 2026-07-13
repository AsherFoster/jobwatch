"""create_user_searches

Searches move out of the "searches" settings row (a JSON list) into one
user_searches row per search, keeping only search_term and location. Jobs
point at the search that found them by id instead of carrying its name.

Revision ID: 4c7cca7a8f81
Revises: a36c95f917fe
Create Date: 2026-07-13 21:44:48.587012

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c7cca7a8f81"
down_revision: str | Sequence[str] | None = "a36c95f917fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

settings = sa.table(
    "settings",
    sa.column("key", sa.Text),
    sa.column("value", sa.Text),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

user_searches = sa.table(
    "user_searches",
    sa.column("id", sa.Integer),
    sa.column("search_term", sa.Text),
    sa.column("location", sa.Text),
)

jobs = sa.table(
    "jobs",
    sa.column("search_id", sa.Integer),
    sa.column("search_name", sa.Text),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_searches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("search_term", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("jobs", sa.Column("search_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    row = bind.execute(sa.select(settings.c.value).where(settings.c.key == "searches")).first()
    for search in json.loads(row.value) if row else []:
        search_id = bind.execute(
            user_searches.insert()
            .values(search_term=search["search_term"], location=search["location"])
            .returning(user_searches.c.id)
        ).scalar_one()
        # Jobs used to carry the name of the search that found them.
        bind.execute(
            jobs.update().where(jobs.c.search_name == search["name"]).values(search_id=search_id)
        )
    bind.execute(sa.delete(settings).where(settings.c.key == "searches"))

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.create_foreign_key("fk_jobs_search_id", "user_searches", ["search_id"], ["id"])
        batch_op.drop_column("search_name")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("jobs", sa.Column("search_name", sa.TEXT(), nullable=True))
    op.execute(
        jobs.update().values(
            search_name=sa.func.coalesce(
                sa.select(user_searches.c.search_term)
                .where(user_searches.c.id == jobs.c.search_id)
                .scalar_subquery(),
                "",
            )
        )
    )

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.alter_column("search_name", existing_type=sa.TEXT(), nullable=False)
        batch_op.drop_constraint("fk_jobs_search_id", type_="foreignkey")
        batch_op.drop_column("search_id")

    bind = op.get_bind()
    rows = bind.execute(sa.select(user_searches).order_by(user_searches.c.id)).mappings().all()
    if rows:
        searches = [
            {"name": r["search_term"], "search_term": r["search_term"], "location": r["location"]}
            for r in rows
        ]
        bind.execute(
            settings.insert().values(
                key="searches", value=json.dumps(searches), updated_at=sa.func.now()
            )
        )
    op.drop_table("user_searches")
