"""broker-neutral asset identity

Revision ID: a545772f76bc
Revises: 3f05d597d2a0
Create Date: 2026-10-11 00:04:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a545772f76bc"
down_revision: Union[str, Sequence[str], None] = "3f05d597d2a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EXISTING_BROKER = "IBKR"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "assets",
        sa.Column(
            "new_asset_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )

    op.create_table(
        "broker_assets",
        sa.Column("broker_id", sa.String(length=100), nullable=False),
        sa.Column("broker_asset_id", sa.String(length=100), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
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
            ["broker_id"],
            ["brokers.broker_id"],
            name=op.f("fk_broker_assets_broker_id_brokers"),
        ),
        sa.PrimaryKeyConstraint(
            "broker_id", "broker_asset_id", name=op.f("pk_broker_assets")
        ),
    )
    op.execute(
        f"""
        INSERT INTO broker_assets (broker_id, broker_asset_id, asset_id)
        SELECT '{EXISTING_BROKER}', asset_id, new_asset_id FROM assets
        """
    )

    op.add_column("orders", sa.Column("new_from_asset_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE orders SET new_from_asset_id = assets.new_asset_id
        FROM assets WHERE assets.asset_id = orders.from_asset_id
        """
    )
    op.drop_index(op.f("ix_orders_from_asset_id"), table_name="orders")
    op.drop_constraint(
        op.f("fk_orders_from_asset_id_assets"), "orders", type_="foreignkey"
    )
    op.drop_column("orders", "from_asset_id")
    op.alter_column(
        "orders", "new_from_asset_id", new_column_name="from_asset_id", nullable=False
    )

    op.drop_constraint(op.f("pk_assets"), "assets", type_="primary")
    op.drop_column("assets", "asset_id")
    op.alter_column(
        "assets", "new_asset_id", new_column_name="asset_id", server_default=None
    )
    op.create_primary_key(op.f("pk_assets"), "assets", ["asset_id"])

    op.create_foreign_key(
        op.f("fk_broker_assets_asset_id_assets"),
        "broker_assets",
        "assets",
        ["asset_id"],
        ["asset_id"],
    )
    op.create_index(
        op.f("ix_broker_assets_asset_id"), "broker_assets", ["asset_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_orders_from_asset_id_assets"),
        "orders",
        "assets",
        ["from_asset_id"],
        ["asset_id"],
    )
    op.create_index(
        op.f("ix_orders_from_asset_id"), "orders", ["from_asset_id"], unique=False
    )

    op.add_column("assets", sa.Column("figi", sa.CHAR(length=12), nullable=True))
    op.create_unique_constraint(op.f("uq_assets_figi"), "assets", ["figi"])
    op.create_check_constraint(
        op.f("ck_assets_figi_format"), "assets", "figi ~ '^BBG[0-9A-Z]{9}$'"
    )
    op.create_index(
        "uq_assets_fx_symbol",
        "assets",
        ["asset_symbol"],
        unique=True,
        postgresql_where=sa.text("asset_category = 'CASH'"),
    )
    op.execute("ALTER TABLE broker_assets ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_assets_fx_symbol", table_name="assets")
    op.drop_constraint(op.f("ck_assets_figi_format"), "assets", type_="check")
    op.drop_constraint(op.f("uq_assets_figi"), "assets", type_="unique")
    op.drop_column("assets", "figi")

    op.add_column("assets", sa.Column("old_asset_id", sa.String(length=16)))
    op.execute(
        f"""
        UPDATE assets SET old_asset_id = broker_assets.broker_asset_id
        FROM broker_assets
        WHERE broker_assets.asset_id = assets.asset_id
          AND broker_assets.broker_id = '{EXISTING_BROKER}'
        """
    )
    op.alter_column("assets", "old_asset_id", nullable=False)

    op.add_column("orders", sa.Column("old_from_asset_id", sa.String(length=16)))
    op.execute(
        """
        UPDATE orders SET old_from_asset_id = assets.old_asset_id
        FROM assets WHERE assets.asset_id = orders.from_asset_id
        """
    )
    op.drop_index(op.f("ix_orders_from_asset_id"), table_name="orders")
    op.drop_constraint(
        op.f("fk_orders_from_asset_id_assets"), "orders", type_="foreignkey"
    )
    op.drop_column("orders", "from_asset_id")
    op.alter_column(
        "orders", "old_from_asset_id", new_column_name="from_asset_id", nullable=False
    )

    op.drop_table("broker_assets")
    op.drop_constraint(op.f("pk_assets"), "assets", type_="primary")
    op.drop_column("assets", "asset_id")
    op.alter_column("assets", "old_asset_id", new_column_name="asset_id")
    op.create_primary_key(op.f("pk_assets"), "assets", ["asset_id"])
    op.create_foreign_key(
        op.f("fk_orders_from_asset_id_assets"),
        "orders",
        "assets",
        ["from_asset_id"],
        ["asset_id"],
    )
    op.create_index(
        op.f("ix_orders_from_asset_id"), "orders", ["from_asset_id"], unique=False
    )
