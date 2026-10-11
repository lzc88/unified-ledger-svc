"""canonical asset ticker not null

Revision ID: 70d0fd3f9ebe
Revises: cf79238265ef
Create Date: 2026-10-12 01:08:33.444199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70d0fd3f9ebe'
down_revision: Union[str, Sequence[str], None] = 'cf79238265ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "canonical_assets",
        "ticker",
        existing_type=sa.String(length=32),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "canonical_assets",
        "ticker",
        existing_type=sa.String(length=32),
        nullable=True,
    )
