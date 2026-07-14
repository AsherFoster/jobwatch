"""add_user_id_to_user_searches

Existing searches are assigned to the first user, if any.

Revision ID: 41bfa88e89b6
Revises: f46b5aaae86e
Create Date: 2026-07-14 12:46:08.866719

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "41bfa88e89b6"
down_revision: str | Sequence[str] | None = "f46b5aaae86e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


users = sa.table("users", sa.column("id", sa.Integer))
user_searches = sa.table("user_searches", sa.column("user_id", sa.Integer))


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("user_searches", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_user_searches_user_id", "user_searches", "users", ["user_id"], ["id"]
    )

    bind = op.get_bind()
    first_user_id = bind.execute(sa.select(users.c.id).order_by(users.c.id).limit(1)).scalar()
    if first_user_id is not None:
        bind.execute(user_searches.update().values(user_id=first_user_id))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_user_searches_user_id", "user_searches", type_="foreignkey")
    op.drop_column("user_searches", "user_id")
