"""canonical asset ticker

Revision ID: cf79238265ef
Revises: 6195636a4026
Create Date: 2026-10-12 01:08:33.288928

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf79238265ef'
down_revision: Union[str, Sequence[str], None] = '6195636a4026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "canonical_assets",
        sa.Column("ticker", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("canonical_assets", "ticker")
