"""cash_accounts

Revision ID: 0705f9d98eec
Revises: ee9df812dfee
Create Date: 2026-11-21 16:54:53.606419

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0705f9d98eec'
down_revision: Union[str, Sequence[str], None] = 'ee9df812dfee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cash_accounts",
        sa.Column("cash_account_id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("institution", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("balance", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("interest_rate", sa.Numeric(), nullable=True),
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
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_cash_accounts_currency_iso")
        ),
        sa.CheckConstraint(
            "balance >= 0", name=op.f("ck_cash_accounts_balance_non_negative")
        ),
        sa.CheckConstraint(
            "interest_rate >= 0 AND interest_rate <= 100",
            name=op.f("ck_cash_accounts_interest_rate_range"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_cash_accounts_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("cash_account_id", name=op.f("pk_cash_accounts")),
        sa.UniqueConstraint(
            "from_user_id",
            "institution",
            "label",
            name=op.f("uq_cash_accounts_from_user_id"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cash_accounts")
