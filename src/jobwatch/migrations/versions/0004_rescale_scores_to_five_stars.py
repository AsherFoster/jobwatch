"""rescale assessment scores from 0-10 to the 1-5 star scale

Scores are now produced on a 1-5 scale (0 reserved for unparseable
responses). Existing 0-10 scores are halved, rounding up, so past
assessments render sensibly as star ratings. Run manually with
`uv run alembic upgrade head` against your deployed DB.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-10 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE assessments SET score = (score + 1) / 2")


def downgrade() -> None:
    # Lossy: the original 0-10 value cannot be recovered exactly.
    op.execute("UPDATE assessments SET score = score * 2")
