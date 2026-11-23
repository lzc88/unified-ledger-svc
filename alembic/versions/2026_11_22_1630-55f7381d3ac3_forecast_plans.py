"""forecast_plans

Revision ID: 55f7381d3ac3
Revises: 7f40e706b433
Create Date: 2026-11-22 16:30:48.777920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '55f7381d3ac3'
down_revision: Union[str, Sequence[str], None] = '7f40e706b433'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "forecast_plans",
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("gross_income", sa.Numeric(), nullable=False),
        sa.Column("end_month", sa.Date(), nullable=False),
        sa.Column("remainder_destination_id", sa.String(length=64), nullable=True),
        sa.Column(
            "destinations", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "gross_income >= 0",
            name=op.f("ck_forecast_plans_gross_income_non_negative"),
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM end_month) = 1",
            name=op.f("ck_forecast_plans_end_month_first_day"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_forecast_plans_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("from_user_id", name=op.f("pk_forecast_plans")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("forecast_plans")
