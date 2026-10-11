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
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
    user_name: Mapped[str] = mapped_column(String(100))


class Account(Timestamped, Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("brokers.broker_id"), primary_key=True
    )
    from_user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("users.user_id"), index=True
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
        # A broker's API credentials are shared, so one active job per broker.
        Index(
            "uq_sync_jobs_active_broker",
            "from_broker_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
        CheckConstraint("start_date <= end_date", name="date_range"),
    )
