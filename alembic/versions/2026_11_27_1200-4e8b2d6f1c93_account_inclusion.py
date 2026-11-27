"""account inclusion

Revision ID: 4e8b2d6f1c93
Revises: 1a7c3e9b5d42
Create Date: 2026-11-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4e8b2d6f1c93'
down_revision: Union[str, Sequence[str], None] = '1a7c3e9b5d42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("account_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "included",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "included")
    op.drop_column("accounts", "account_name")
