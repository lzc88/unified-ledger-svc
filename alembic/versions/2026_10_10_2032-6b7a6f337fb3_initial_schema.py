"""initial schema

Revision ID: 6b7a6f337fb3
Revises:
Create Date: 2026-10-10 20:32:03.519738

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6b7a6f337fb3"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("assets", "brokers", "users", "accounts", "cash", "orders", "trades", "fees")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(length=16), nullable=False),
        sa.Column("asset_symbol", sa.String(length=16), nullable=False),
        sa.Column("listing_exchange", sa.String(length=16), nullable=True),
        sa.Column(
            "asset_category",
            sa.Enum(
                "STOCK",
                "ETF",
                "CASH",
                name="asset_category",
                native_enum=False,
                create_constraint=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
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
            "asset_category IN ('STOCK', 'ETF', 'CASH')",
            name=op.f("ck_assets_asset_category"),
        ),
        sa.PrimaryKeyConstraint("asset_id", name=op.f("pk_assets")),
    )
    op.create_table(
        "brokers",
        sa.Column("broker_id", sa.String(length=100), nullable=False),
        sa.Column("broker_name", sa.String(length=100), nullable=False),
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
        sa.PrimaryKeyConstraint("broker_id", name=op.f("pk_brokers")),
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("user_name", sa.String(length=100), nullable=False),
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
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_users")),
    )
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_user_id", sa.String(length=100), nullable=False),
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
            ["from_broker_id"],
            ["brokers.broker_id"],
            name=op.f("fk_accounts_from_broker_id_brokers"),
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.user_id"],
            name=op.f("fk_accounts_from_user_id_users"),
        ),
        sa.PrimaryKeyConstraint(
            "account_id", "from_broker_id", name=op.f("pk_accounts")
        ),
    )
    op.create_index(
        op.f("ix_accounts_from_user_id"), "accounts", ["from_user_id"], unique=False
    )
    op.create_table(
        "cash",
        sa.Column("tx_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_account_id", sa.String(length=100), nullable=False),
        sa.Column("tx_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tx_amount", sa.Numeric(), nullable=False),
        sa.Column("tx_currency", sa.CHAR(length=3), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "DEPOSIT",
                "WITHDRAW",
                name="action",
                native_enum=False,
                create_constraint=False,
                length=16,
            ),
            nullable=False,
        ),
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
            "action IN ('DEPOSIT', 'WITHDRAW')", name=op.f("ck_cash_action")
        ),
        sa.CheckConstraint(
            "tx_currency ~ '^[A-Z]{3}$'", name=op.f("ck_cash_tx_currency_iso")
        ),
        sa.CheckConstraint("tx_amount > 0", name=op.f("ck_cash_tx_amount_positive")),
        sa.ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            name=op.f("fk_cash_from_account_id_accounts"),
        ),
        sa.PrimaryKeyConstraint("tx_id", "from_broker_id", name=op.f("pk_cash")),
    )
    op.create_index(
        "ix_cash_account", "cash", ["from_account_id", "from_broker_id"], unique=False
    )
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_account_id", sa.String(length=100), nullable=False),
        sa.Column("from_asset_id", sa.String(length=16), nullable=False),
        sa.Column("order_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "BUY",
                "SELL",
                name="action",
                native_enum=False,
                create_constraint=False,
                length=16,
            ),
            nullable=False,
        ),
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
        sa.CheckConstraint("action IN ('BUY', 'SELL')", name=op.f("ck_orders_action")),
        sa.ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            name=op.f("fk_orders_from_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["from_asset_id"],
            ["assets.asset_id"],
            name=op.f("fk_orders_from_asset_id_assets"),
        ),
        sa.PrimaryKeyConstraint("order_id", "from_broker_id", name=op.f("pk_orders")),
    )
    op.create_index(
        "ix_orders_account",
        "orders",
        ["from_account_id", "from_broker_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orders_from_asset_id"), "orders", ["from_asset_id"], unique=False
    )
    op.create_table(
        "trades",
        sa.Column("trade_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_order_id", sa.String(length=100), nullable=False),
        sa.Column("trade_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_amount", sa.Numeric(), nullable=False),
        sa.Column("trade_quantity", sa.Numeric(), nullable=False),
        sa.Column("trade_price", sa.Numeric(), nullable=False),
        sa.Column("trade_currency", sa.CHAR(length=3), nullable=False),
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
            "trade_currency ~ '^[A-Z]{3}$'", name=op.f("ck_trades_trade_currency_iso")
        ),
        sa.CheckConstraint(
            "trade_amount >= 0", name=op.f("ck_trades_trade_amount_non_negative")
        ),
        sa.CheckConstraint(
            "trade_price >= 0", name=op.f("ck_trades_trade_price_non_negative")
        ),
        sa.CheckConstraint(
            "trade_quantity > 0", name=op.f("ck_trades_trade_quantity_positive")
        ),
        sa.ForeignKeyConstraint(
            ["from_order_id", "from_broker_id"],
            ["orders.order_id", "orders.from_broker_id"],
            name=op.f("fk_trades_from_order_id_orders"),
        ),
        sa.PrimaryKeyConstraint("trade_id", "from_broker_id", name=op.f("pk_trades")),
    )
    op.create_index(
        "ix_trades_order", "trades", ["from_order_id", "from_broker_id"], unique=False
    )
    op.create_table(
        "fees",
        sa.Column("from_trade_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column(
            "fee_type",
            sa.Enum(
                "COMMISSION",
                "TAX",
                name="fee_type",
                native_enum=False,
                create_constraint=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("fee_amount", sa.Numeric(), nullable=False),
        sa.Column("fee_currency", sa.CHAR(length=3), nullable=False),
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
            "fee_currency ~ '^[A-Z]{3}$'", name=op.f("ck_fees_fee_currency_iso")
        ),
        sa.CheckConstraint(
            "fee_type IN ('COMMISSION', 'TAX')", name=op.f("ck_fees_fee_type")
        ),
        sa.CheckConstraint("fee_amount > 0", name=op.f("ck_fees_fee_amount_positive")),
        sa.ForeignKeyConstraint(
            ["from_trade_id", "from_broker_id"],
            ["trades.trade_id", "trades.from_broker_id"],
            name=op.f("fk_fees_from_trade_id_trades"),
        ),
        sa.PrimaryKeyConstraint(
            "from_trade_id", "from_broker_id", "fee_type", name=op.f("pk_fees")
        ),
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("fees")
    op.drop_index("ix_trades_order", table_name="trades")
    op.drop_table("trades")
    op.drop_index(op.f("ix_orders_from_asset_id"), table_name="orders")
    op.drop_index("ix_orders_account", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_cash_account", table_name="cash")
    op.drop_table("cash")
    op.drop_index(op.f("ix_accounts_from_user_id"), table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("users")
    op.drop_table("brokers")
    op.drop_table("assets")
