import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from config.config import CASH_CURRENCIES

from .db import Base

Amount = Numeric()


class ListingCategory(enum.StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"


class CashAction(enum.StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"


class OrderAction(enum.StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class FeeType(enum.StrEnum):
    COMMISSION = "COMMISSION"
    TAX = "TAX"


class SyncKind(enum.StrEnum):
    BACKFILL = "BACKFILL"
    REFRESH = "REFRESH"


class SyncStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


ACTIVE_SYNC_STATUSES = (SyncStatus.PENDING, SyncStatus.RUNNING)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, native_enum=False, create_constraint=True, length=16)


def _currency_check(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} ~ '^[A-Z]{{3}}$'", name=f"{column}_iso")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CanonicalAsset(Timestamped, Base):
    __tablename__ = "canonical_assets"

    trading_venue_figi: Mapped[str] = mapped_column(String(100), primary_key=True)
    composite_figi: Mapped[str | None] = mapped_column(String(100))
    share_class_figi: Mapped[str | None] = mapped_column(String(100))
    ticker: Mapped[str] = mapped_column(String(32))
    listing_category: Mapped[ListingCategory] = mapped_column(
        _enum(ListingCategory, "listing_category")
    )
    listing_exchange: Mapped[str] = mapped_column(String(16))
    listing_currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (_currency_check("listing_currency"),)


class Broker(Timestamped, Base):
    __tablename__ = "brokers"

    broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    broker_name: Mapped[str] = mapped_column(String(100))


class BrokerAsset(Timestamped, Base):
    __tablename__ = "broker_assets"

    broker_asset_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("brokers.broker_id"), primary_key=True
    )
    from_asset_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("canonical_assets.trading_venue_figi"), index=True
    )


class User(Timestamped, Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_name: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class UserSession(Timestamped, Base):
    __tablename__ = "user_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserConfig(Timestamped, Base):
    __tablename__ = "user_configs"

    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), primary_key=True
    )
    config_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    encrypted_value: Mapped[str] = mapped_column(Text)


class CashAccount(Timestamped, Base):
    __tablename__ = "cash_accounts"

    cash_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id")
    )
    label: Mapped[str] = mapped_column(String(100))
    balance: Mapped[Decimal] = mapped_column(Amount)
    currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        UniqueConstraint("from_user_id", "label"),
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint(
            f"currency IN ({_quoted(CASH_CURRENCIES)})", name="currency_allowed"
        ),
    )


class CpfStatement(Timestamped, Base):
    __tablename__ = "cpf_statements"

    statement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), unique=True
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    opening_oa: Mapped[Decimal] = mapped_column(Amount)
    opening_sa: Mapped[Decimal] = mapped_column(Amount)
    opening_ma: Mapped[Decimal] = mapped_column(Amount)
    closing_oa: Mapped[Decimal] = mapped_column(Amount)
    closing_sa: Mapped[Decimal] = mapped_column(Amount)
    closing_ma: Mapped[Decimal] = mapped_column(Amount)

    __table_args__ = (
        CheckConstraint("period_start <= period_end", name="period_range"),
    )


class CpfTransaction(Timestamped, Base):
    __tablename__ = "cpf_transactions"

    cpf_tx_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    from_statement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cpf_statements.statement_id", ondelete="CASCADE"),
    )
    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id")
    )
    line_no: Mapped[int] = mapped_column(Integer)
    tx_date: Mapped[date] = mapped_column(Date)
    code: Mapped[str] = mapped_column(String(3))
    contribution_month: Mapped[date | None] = mapped_column(Date)
    employer: Mapped[str | None] = mapped_column(String(200))
    oa_amount: Mapped[Decimal] = mapped_column(Amount)
    sa_amount: Mapped[Decimal] = mapped_column(Amount)
    ma_amount: Mapped[Decimal] = mapped_column(Amount)

    __table_args__ = (
        Index("ix_cpf_transactions_user_date", "from_user_id", "tx_date"),
        UniqueConstraint("from_statement_id", "line_no"),
        CheckConstraint("code ~ '^[A-Z]{2,3}$'", name="code_format"),
        CheckConstraint(
            "EXTRACT(DAY FROM contribution_month) = 1",
            name="contribution_month_first_day",
        ),
    )


class ForecastPlan(Timestamped, Base):
    __tablename__ = "forecast_plans"

    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), primary_key=True
    )
    gross_income: Mapped[Decimal] = mapped_column(Amount)
    end_month: Mapped[date] = mapped_column(Date)
    remainder_destination_id: Mapped[str | None] = mapped_column(String(64))
    destinations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint("gross_income >= 0", name="gross_income_non_negative"),
        CheckConstraint(
            "EXTRACT(DAY FROM end_month) = 1", name="end_month_first_day"
        ),
    )


class BrokerConnection(Timestamped, Base):
    __tablename__ = "broker_connections"

    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), primary_key=True
    )
    from_broker_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("brokers.broker_id"), primary_key=True
    )
    credentials: Mapped[str] = mapped_column(Text)


class Account(Timestamped, Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("brokers.broker_id"), primary_key=True
    )
    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), index=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_user_id", "from_broker_id"],
            ["broker_connections.from_user_id", "broker_connections.from_broker_id"],
        ),
    )


class ExecutedCash(Timestamped, Base):
    __tablename__ = "executed_cash"

    cash_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100))
    tx_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[CashAction] = mapped_column(_enum(CashAction, "action"))
    tx_amount: Mapped[Decimal] = mapped_column(Amount)
    tx_currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
        ),
        Index("ix_executed_cash_account", "from_account_id", "from_broker_id"),
        CheckConstraint("tx_amount > 0", name="tx_amount_positive"),
        _currency_check("tx_currency"),
    )


class ExecutedTradeOrder(Timestamped, Base):
    __tablename__ = "executed_trade_orders"

    trade_order_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100))
    from_broker_asset_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[OrderAction] = mapped_column(_enum(OrderAction, "action"))
    order_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
        ),
        ForeignKeyConstraint(
            ["from_broker_asset_id", "from_broker_id"],
            ["broker_assets.broker_asset_id", "broker_assets.from_broker_id"],
        ),
        Index("ix_executed_trade_orders_account", "from_account_id", "from_broker_id"),
        Index(
            "ix_executed_trade_orders_broker_asset",
            "from_broker_asset_id",
            "from_broker_id",
        ),
    )


class ExecutedTrade(Timestamped, Base):
    __tablename__ = "executed_trades"

    trade_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_trade_order_id: Mapped[str] = mapped_column(String(100))
    trade_amount: Mapped[Decimal] = mapped_column(Amount)
    trade_quantity: Mapped[Decimal] = mapped_column(Amount)
    trade_price: Mapped[Decimal] = mapped_column(Amount)
    trade_currency: Mapped[str] = mapped_column(CHAR(3))
    trade_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_trade_order_id", "from_broker_id"],
            [
                "executed_trade_orders.trade_order_id",
                "executed_trade_orders.from_broker_id",
            ],
        ),
        Index("ix_executed_trades_order", "from_trade_order_id", "from_broker_id"),
        CheckConstraint("trade_amount >= 0", name="trade_amount_non_negative"),
        CheckConstraint("trade_quantity > 0", name="trade_quantity_positive"),
        CheckConstraint("trade_price >= 0", name="trade_price_non_negative"),
        _currency_check("trade_currency"),
    )


class TradeFee(Timestamped, Base):
    __tablename__ = "trade_fees"

    from_trade_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    trade_fee_type: Mapped[FeeType] = mapped_column(
        _enum(FeeType, "trade_fee_type"), primary_key=True
    )
    trade_fee_amount: Mapped[Decimal] = mapped_column(Amount)
    trade_fee_currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_trade_id", "from_broker_id"],
            ["executed_trades.trade_id", "executed_trades.from_broker_id"],
        ),
        CheckConstraint("trade_fee_amount > 0", name="trade_fee_amount_positive"),
        _currency_check("trade_fee_currency"),
    )


class CanonicalFx(Timestamped, Base):
    __tablename__ = "canonical_fx"

    fx_pair_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    fx_long_currency: Mapped[str] = mapped_column(CHAR(3))
    fx_short_currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        _currency_check("fx_long_currency"),
        _currency_check("fx_short_currency"),
    )


class ExecutedFxOrder(Timestamped, Base):
    __tablename__ = "executed_fx_orders"

    fx_order_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100))
    from_fx_pair_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("canonical_fx.fx_pair_id"), index=True
    )
    action: Mapped[OrderAction] = mapped_column(_enum(OrderAction, "action"))
    order_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
        ),
        Index("ix_executed_fx_orders_account", "from_account_id", "from_broker_id"),
    )


class ExecutedFx(Timestamped, Base):
    __tablename__ = "executed_fx"

    fx_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_fx_order_id: Mapped[str] = mapped_column(String(100))
    fx_amount: Mapped[Decimal] = mapped_column(Amount)
    fx_quantity: Mapped[Decimal] = mapped_column(Amount)
    fx_price: Mapped[Decimal] = mapped_column(Amount)
    fx_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_fx_order_id", "from_broker_id"],
            ["executed_fx_orders.fx_order_id", "executed_fx_orders.from_broker_id"],
        ),
        Index("ix_executed_fx_order", "from_fx_order_id", "from_broker_id"),
        CheckConstraint("fx_amount >= 0", name="fx_amount_non_negative"),
        CheckConstraint("fx_quantity > 0", name="fx_quantity_positive"),
        CheckConstraint("fx_price >= 0", name="fx_price_non_negative"),
    )


class FxFee(Timestamped, Base):
    __tablename__ = "fx_fees"

    from_fx_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    fx_fee_type: Mapped[FeeType] = mapped_column(
        _enum(FeeType, "fx_fee_type"), primary_key=True
    )
    fx_fee_amount: Mapped[Decimal] = mapped_column(Amount)
    fx_fee_currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_fx_id", "from_broker_id"],
            ["executed_fx.fx_id", "executed_fx.from_broker_id"],
        ),
        CheckConstraint("fx_fee_amount > 0", name="fx_fee_amount_positive"),
        _currency_check("fx_fee_currency"),
    )


class SyncJob(Timestamped, Base):
    """One backfill/refresh of a user's ledger from a broker."""

    __tablename__ = "sync_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), index=True
    )
    from_broker_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("brokers.broker_id")
    )
    kind: Mapped[SyncKind] = mapped_column(_enum(SyncKind, "kind"))
    status: Mapped[SyncStatus] = mapped_column(
        _enum(SyncStatus, "status"), default=SyncStatus.PENDING
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    inserted: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    skipped: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_user_id", "from_broker_id"],
            ["broker_connections.from_user_id", "broker_connections.from_broker_id"],
        ),
        Index(
            "uq_sync_jobs_active_connection",
            "from_user_id",
            "from_broker_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
        CheckConstraint("start_date <= end_date", name="date_range"),
    )
