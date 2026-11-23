"""sync skipped

Revision ID: 1a7c3e9b5d42
Revises: 0904411444b4
Create Date: 2026-11-23 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '1a7c3e9b5d42'
down_revision: Union[str, Sequence[str], None] = '0904411444b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broker_connections",
        sa.Column(
            "last_sync_skipped",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("broker_connections", "last_sync_skipped")
