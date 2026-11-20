"""auth

Revision ID: f552982d827a
Revises: 70d0fd3f9ebe
Create Date: 2026-11-20 22:37:46.344620

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f552982d827a'
down_revision: Union[str, Sequence[str], None] = '70d0fd3f9ebe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USER_OWNED_TABLES = (
    "fx_fees",
    "executed_fx",
    "executed_fx_orders",
    "trade_fees",
    "executed_trades",
    "executed_trade_orders",
    "executed_cash",
    "accounts",
    "sync_jobs",
    "users",
)


def upgrade() -> None:
    """Upgrade schema."""
    for table in USER_OWNED_TABLES:
        op.execute(sa.text(f"DELETE FROM {table}"))

    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=False)
    )
    op.create_unique_constraint(op.f("uq_users_user_name"), "users", ["user_name"])

    op.create_table(
        "user_sessions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_user_sessions_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_user_sessions")),
    )
    op.create_index(
        op.f("ix_user_sessions_from_user_id"),
        "user_sessions",
        ["from_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_sessions_from_user_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_constraint(op.f("uq_users_user_name"), "users", type_="unique")
    op.drop_column("users", "password_hash")
