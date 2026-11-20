"""user_configs

Revision ID: ee9df812dfee
Revises: f552982d827a
Create Date: 2026-11-20 23:29:19.863983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee9df812dfee'
down_revision: Union[str, Sequence[str], None] = 'f552982d827a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_configs",
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
        sa.Column("config_key", sa.String(length=64), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
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
            name=op.f("fk_user_configs_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint(
            "from_user_id", "config_key", name=op.f("pk_user_configs")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user_configs")
