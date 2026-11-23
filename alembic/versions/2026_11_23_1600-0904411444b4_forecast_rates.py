"""forecast rates

Revision ID: 0904411444b4
Revises: 8d2dcf762f11
Create Date: 2026-11-23 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0904411444b4'
down_revision: Union[str, Sequence[str], None] = '8d2dcf762f11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DELETE FROM forecast_plans")

    op.add_column(
        "forecast_plans",
        sa.Column(
            "rates",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("forecast_plans", "rates")
