"""canonical ledger

Revision ID: 6195636a4026
Revises: a545772f76bc
Create Date: 2026-10-11 22:26:41.318796

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6195636a4026"
down_revision: Union[str, Sequence[str], None] = "a545772f76bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TABLES = ("fees", "trades", "orders", "cash", "broker_assets", "assets")
NEW_TABLES = (
    "canonical_assets",
    "broker_assets",
    "executed_cash",
    "executed_trade_orders",
    "executed_trades",
    "trade_fees",
    "canonical_fx",
    "executed_fx_orders",
    "executed_fx",
    "fx_fees",
)


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(
        *values, name=name, native_enum=False, create_constraint=False, length=16
    )


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


def _currency_check(table: str, column: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} ~ '^[A-Z]{{3}}$'", name=op.f(f"ck_{table}_{column}_iso")
    )


def upgrade() -> None:
    """Upgrade schema."""
    for table in OLD_TABLES:
        op.drop_table(table)

    op.create_table(
        "canonical_assets",
        sa.Column("trading_venue_figi", sa.String(length=100), nullable=False),
        sa.Column("composite_figi", sa.String(length=100), nullable=True),
        sa.Column("share_class_figi", sa.String(length=100), nullable=True),
        sa.Column(
            "listing_category",
            _enum("STOCK", "ETF", name="listing_category"),
            nullable=False,
        ),
        sa.Column("listing_exchange", sa.String(length=16), nullable=False),
        sa.Column("listing_currency", sa.CHAR(length=3), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "listing_category IN ('STOCK', 'ETF')",
            name=op.f("ck_canonical_assets_listing_category"),
        ),
        _currency_check("canonical_assets", "listing_currency"),
        sa.PrimaryKeyConstraint("trading_venue_figi", name=op.f("pk_canonical_assets")),
    )
    op.create_table(
        "broker_assets",
        sa.Column("broker_asset_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_asset_id", sa.String(length=100), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["from_broker_id"],
            ["brokers.broker_id"],
            name=op.f("fk_broker_assets_from_broker_id_brokers"),
        ),
        sa.ForeignKeyConstraint(
            ["from_asset_id"],
            ["canonical_assets.trading_venue_figi"],
            name=op.f("fk_broker_assets_from_asset_id_canonical_assets"),
        ),
        sa.PrimaryKeyConstraint(
            "broker_asset_id", "from_broker_id", name=op.f("pk_broker_assets")
        ),
    )
    op.create_index(
        op.f("ix_broker_assets_from_asset_id"),
        "broker_assets",
        ["from_asset_id"],
        unique=False,
    )

    op.create_table(
        "executed_cash",
        sa.Column("cash_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_account_id", sa.String(length=100), nullable=False),
        sa.Column("tx_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "action", _enum("DEPOSIT", "WITHDRAW", name="action"), nullable=False
        ),
        sa.Column("tx_amount", sa.Numeric(), nullable=False),
        sa.Column("tx_currency", sa.CHAR(length=3), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "action IN ('DEPOSIT', 'WITHDRAW')", name=op.f("ck_executed_cash_action")
        ),
        sa.CheckConstraint(
            "tx_amount > 0", name=op.f("ck_executed_cash_tx_amount_positive")
        ),
        _currency_check("executed_cash", "tx_currency"),
        sa.ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            name=op.f("fk_executed_cash_from_account_id_accounts"),
        ),
        sa.PrimaryKeyConstraint(
            "cash_id", "from_broker_id", name=op.f("pk_executed_cash")
        ),
    )
    op.create_index(
        "ix_executed_cash_account",
        "executed_cash",
        ["from_account_id", "from_broker_id"],
        unique=False,
    )

    op.create_table(
        "executed_trade_orders",
        sa.Column("trade_order_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_account_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_asset_id", sa.String(length=100), nullable=False),
        sa.Column("action", _enum("BUY", "SELL", name="action"), nullable=False),
        sa.Column("order_datetime", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "action IN ('BUY', 'SELL')", name=op.f("ck_executed_trade_orders_action")
        ),
        sa.ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            name=op.f("fk_executed_trade_orders_from_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["from_broker_asset_id", "from_broker_id"],
            ["broker_assets.broker_asset_id", "broker_assets.from_broker_id"],
            name=op.f("fk_executed_trade_orders_from_broker_asset_id_broker_assets"),
        ),
        sa.PrimaryKeyConstraint(
            "trade_order_id", "from_broker_id", name=op.f("pk_executed_trade_orders")
        ),
    )
    op.create_index(
        "ix_executed_trade_orders_account",
        "executed_trade_orders",
        ["from_account_id", "from_broker_id"],
        unique=False,
    )
    op.create_index(
        "ix_executed_trade_orders_broker_asset",
        "executed_trade_orders",
        ["from_broker_asset_id", "from_broker_id"],
        unique=False,
    )

    op.create_table(
        "executed_trades",
        sa.Column("trade_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_trade_order_id", sa.String(length=100), nullable=False),
        sa.Column("trade_amount", sa.Numeric(), nullable=False),
        sa.Column("trade_quantity", sa.Numeric(), nullable=False),
        sa.Column("trade_price", sa.Numeric(), nullable=False),
        sa.Column("trade_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("trade_datetime", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "trade_amount >= 0",
            name=op.f("ck_executed_trades_trade_amount_non_negative"),
        ),
        sa.CheckConstraint(
            "trade_quantity > 0",
            name=op.f("ck_executed_trades_trade_quantity_positive"),
        ),
        sa.CheckConstraint(
            "trade_price >= 0", name=op.f("ck_executed_trades_trade_price_non_negative")
        ),
        _currency_check("executed_trades", "trade_currency"),
        sa.ForeignKeyConstraint(
            ["from_trade_order_id", "from_broker_id"],
            [
                "executed_trade_orders.trade_order_id",
                "executed_trade_orders.from_broker_id",
            ],
            name=op.f("fk_executed_trades_from_trade_order_id_executed_trade_orders"),
        ),
        sa.PrimaryKeyConstraint(
            "trade_id", "from_broker_id", name=op.f("pk_executed_trades")
        ),
    )
    op.create_index(
        "ix_executed_trades_order",
        "executed_trades",
        ["from_trade_order_id", "from_broker_id"],
        unique=False,
    )

    op.create_table(
        "trade_fees",
        sa.Column("from_trade_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column(
            "trade_fee_type",
            _enum("COMMISSION", "TAX", name="trade_fee_type"),
            nullable=False,
        ),
        sa.Column("trade_fee_amount", sa.Numeric(), nullable=False),
        sa.Column("trade_fee_currency", sa.CHAR(length=3), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "trade_fee_type IN ('COMMISSION', 'TAX')",
            name=op.f("ck_trade_fees_trade_fee_type"),
        ),
        sa.CheckConstraint(
            "trade_fee_amount > 0", name=op.f("ck_trade_fees_trade_fee_amount_positive")
        ),
        _currency_check("trade_fees", "trade_fee_currency"),
        sa.ForeignKeyConstraint(
            ["from_trade_id", "from_broker_id"],
            ["executed_trades.trade_id", "executed_trades.from_broker_id"],
            name=op.f("fk_trade_fees_from_trade_id_executed_trades"),
        ),
        sa.PrimaryKeyConstraint(
            "from_trade_id",
            "from_broker_id",
            "trade_fee_type",
            name=op.f("pk_trade_fees"),
        ),
    )

    op.create_table(
        "canonical_fx",
        sa.Column("fx_pair_id", sa.String(length=16), nullable=False),
        sa.Column("fx_long_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("fx_short_currency", sa.CHAR(length=3), nullable=False),
        *_timestamps(),
        _currency_check("canonical_fx", "fx_long_currency"),
        _currency_check("canonical_fx", "fx_short_currency"),
        sa.PrimaryKeyConstraint("fx_pair_id", name=op.f("pk_canonical_fx")),
    )

    op.create_table(
        "executed_fx_orders",
        sa.Column("fx_order_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_account_id", sa.String(length=100), nullable=False),
        sa.Column("from_fx_pair_id", sa.String(length=16), nullable=False),
        sa.Column("action", _enum("BUY", "SELL", name="action"), nullable=False),
        sa.Column("order_datetime", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "action IN ('BUY', 'SELL')", name=op.f("ck_executed_fx_orders_action")
        ),
        sa.ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            name=op.f("fk_executed_fx_orders_from_account_id_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["from_fx_pair_id"],
            ["canonical_fx.fx_pair_id"],
            name=op.f("fk_executed_fx_orders_from_fx_pair_id_canonical_fx"),
        ),
        sa.PrimaryKeyConstraint(
            "fx_order_id", "from_broker_id", name=op.f("pk_executed_fx_orders")
        ),
    )
    op.create_index(
        "ix_executed_fx_orders_account",
        "executed_fx_orders",
        ["from_account_id", "from_broker_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_executed_fx_orders_from_fx_pair_id"),
        "executed_fx_orders",
        ["from_fx_pair_id"],
        unique=False,
    )

    op.create_table(
        "executed_fx",
        sa.Column("fx_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column("from_fx_order_id", sa.String(length=100), nullable=False),
        sa.Column("fx_amount", sa.Numeric(), nullable=False),
        sa.Column("fx_quantity", sa.Numeric(), nullable=False),
        sa.Column("fx_price", sa.Numeric(), nullable=False),
        sa.Column("fx_datetime", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "fx_amount >= 0", name=op.f("ck_executed_fx_fx_amount_non_negative")
        ),
        sa.CheckConstraint(
            "fx_quantity > 0", name=op.f("ck_executed_fx_fx_quantity_positive")
        ),
        sa.CheckConstraint(
            "fx_price >= 0", name=op.f("ck_executed_fx_fx_price_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["from_fx_order_id", "from_broker_id"],
            ["executed_fx_orders.fx_order_id", "executed_fx_orders.from_broker_id"],
            name=op.f("fk_executed_fx_from_fx_order_id_executed_fx_orders"),
        ),
        sa.PrimaryKeyConstraint("fx_id", "from_broker_id", name=op.f("pk_executed_fx")),
    )
    op.create_index(
        "ix_executed_fx_order",
        "executed_fx",
        ["from_fx_order_id", "from_broker_id"],
        unique=False,
    )

    op.create_table(
        "fx_fees",
        sa.Column("from_fx_id", sa.String(length=100), nullable=False),
        sa.Column("from_broker_id", sa.String(length=100), nullable=False),
        sa.Column(
            "fx_fee_type",
            _enum("COMMISSION", "TAX", name="fx_fee_type"),
            nullable=False,
        ),
        sa.Column("fx_fee_amount", sa.Numeric(), nullable=False),
        sa.Column("fx_fee_currency", sa.CHAR(length=3), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "fx_fee_type IN ('COMMISSION', 'TAX')", name=op.f("ck_fx_fees_fx_fee_type")
        ),
        sa.CheckConstraint(
            "fx_fee_amount > 0", name=op.f("ck_fx_fees_fx_fee_amount_positive")
        ),
        _currency_check("fx_fees", "fx_fee_currency"),
        sa.ForeignKeyConstraint(
            ["from_fx_id", "from_broker_id"],
            ["executed_fx.fx_id", "executed_fx.from_broker_id"],
            name=op.f("fk_fx_fees_from_fx_id_executed_fx"),
        ),
        sa.PrimaryKeyConstraint(
            "from_fx_id", "from_broker_id", "fx_fee_type", name=op.f("pk_fx_fees")
        ),
    )

    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(NEW_TABLES):
        op.drop_table(table)

    op.create_table(
        "assets",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("asset_symbol", sa.String(length=16), nullable=False),
        sa.Column("listing_exchange", sa.String(length=16), nullable=True),
        sa.Column(
            "asset_category",
            _enum("STOCK", "ETF", "CASH", name="asset_category"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("figi", sa.CHAR(length=12), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "asset_category IN ('STOCK', 'ETF', 'CASH')",
            name=op.f("ck_assets_asset_category"),
        ),
        sa.CheckConstraint(
            "figi ~ '^BBG[0-9A-Z]{9}$'", name=op.f("ck_assets_figi_format")
        ),
        sa.PrimaryKeyConstraint("asset_id", name=op.f("pk_assets")),
        sa.UniqueConstraint("figi", name=op.f("uq_assets_figi")),
    )
    op.create_index(
        "uq_assets_fx_symbol",
        "assets",
        ["asset_symbol"],
        unique=True,
        postgresql_where=sa.text("asset_category = 'CASH'"),
    )

    op.create_table(
        "broker_assets",
        sa.Column("broker_id", sa.String(length=100), nullable=False),
        sa.Column("broker_asset_id", sa.String(length=100), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["broker_id"],
            ["brokers.broker_id"],
            name=op.f("fk_broker_assets_broker_id_brokers"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name=op.f("fk_broker_assets_asset_id_assets"),
        ),
        sa.PrimaryKeyConstraint(
            "broker_id", "broker_asset_id", name=op.f("pk_broker_assets")
        ),
    )
    op.create_index(
        op.f("ix_broker_assets_asset_id"), "broker_assets", ["asset_id"], unique=False
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
            "action", _enum("DEPOSIT", "WITHDRAW", name="action"), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "action IN ('DEPOSIT', 'WITHDRAW')", name=op.f("ck_cash_action")
        ),
        _currency_check("cash", "tx_currency"),
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
        sa.Column("from_asset_id", sa.Uuid(), nullable=False),
        sa.Column("order_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", _enum("BUY", "SELL", name="action"), nullable=False),
        *_timestamps(),
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
        *_timestamps(),
        _currency_check("trades", "trade_currency"),
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
            "fee_type", _enum("COMMISSION", "TAX", name="fee_type"), nullable=False
        ),
        sa.Column("fee_amount", sa.Numeric(), nullable=False),
        sa.Column("fee_currency", sa.CHAR(length=3), nullable=False),
        *_timestamps(),
        _currency_check("fees", "fee_currency"),
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

    for table in reversed(OLD_TABLES):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
