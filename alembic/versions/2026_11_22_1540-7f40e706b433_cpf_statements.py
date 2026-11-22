"""cpf_statements

Revision ID: 7f40e706b433
Revises: 0705f9d98eec
Create Date: 2026-11-22 15:40:13.132497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f40e706b433'
down_revision: Union[str, Sequence[str], None] = '0705f9d98eec'
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
        "cpf_statements",
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("opening_oa", sa.Numeric(), nullable=False),
        sa.Column("opening_sa", sa.Numeric(), nullable=False),
        sa.Column("opening_ma", sa.Numeric(), nullable=False),
        sa.Column("closing_oa", sa.Numeric(), nullable=False),
        sa.Column("closing_sa", sa.Numeric(), nullable=False),
        sa.Column("closing_ma", sa.Numeric(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "period_start <= period_end", name=op.f("ck_cpf_statements_period_range")
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_cpf_statements_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("statement_id", name=op.f("pk_cpf_statements")),
        sa.UniqueConstraint(
            "from_user_id", name=op.f("uq_cpf_statements_from_user_id")
        ),
    )

    op.create_table(
        "cpf_transactions",
        sa.Column("cpf_tx_id", sa.Uuid(), nullable=False),
        sa.Column("from_statement_id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("tx_date", sa.Date(), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("contribution_month", sa.Date(), nullable=True),
        sa.Column("employer", sa.String(length=200), nullable=True),
        sa.Column("oa_amount", sa.Numeric(), nullable=False),
        sa.Column("sa_amount", sa.Numeric(), nullable=False),
        sa.Column("ma_amount", sa.Numeric(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "code ~ '^[A-Z]{2,3}$'", name=op.f("ck_cpf_transactions_code_format")
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM contribution_month) = 1",
            name=op.f("ck_cpf_transactions_contribution_month_first_day"),
        ),
        sa.ForeignKeyConstraint(
            ["from_statement_id"],
            ["cpf_statements.statement_id"],
            name=op.f("fk_cpf_transactions_from_statement_id_cpf_statements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_cpf_transactions_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("cpf_tx_id", name=op.f("pk_cpf_transactions")),
        sa.UniqueConstraint(
            "from_statement_id",
            "line_no",
            name=op.f("uq_cpf_transactions_from_statement_id"),
        ),
    )

    op.create_index(
        "ix_cpf_transactions_user_date",
        "cpf_transactions",
        ["from_user_id", "tx_date"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_cpf_transactions_user_date", table_name="cpf_transactions")
    op.drop_table("cpf_transactions")
    op.drop_table("cpf_statements")
