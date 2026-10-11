"""create urls table

Revision ID: 6c49dadb8260
Revises: 
Create Date: 2026-10-12 04:42:43.495794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c49dadb8260'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "urls",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "short_code",
            sa.String(length=8),
            nullable=False,
        ),
        sa.Column(
            "original_url",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_code"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("urls")
