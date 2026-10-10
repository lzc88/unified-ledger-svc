import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

Amount = Numeric()


class AssetCategory(enum.StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"
    CASH = "CASH"


class CashAction(enum.StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"


class OrderAction(enum.StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class FeeType(enum.StrEnum):
    COMMISSION = "COMMISSION"
    TAX = "TAX"


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


class Asset(Timestamped, Base):
    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    asset_symbol: Mapped[str] = mapped_column(String(16))
    listing_exchange: Mapped[str | None] = mapped_column(String(16))
    asset_category: Mapped[AssetCategory] = mapped_column(
        _enum(AssetCategory, "asset_category")
    )
    description: Mapped[str | None] = mapped_column(Text)


class Broker(Timestamped, Base):
    __tablename__ = "brokers"

    broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    broker_name: Mapped[str] = mapped_column(String(100))


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


class Cash(Timestamped, Base):
    __tablename__ = "cash"

    tx_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100))
    tx_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tx_amount: Mapped[Decimal] = mapped_column(Amount)
    tx_currency: Mapped[str] = mapped_column(CHAR(3))
    action: Mapped[CashAction] = mapped_column(_enum(CashAction, "action"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
        ),
        Index("ix_cash_account", "from_account_id", "from_broker_id"),
        CheckConstraint("tx_amount > 0", name="tx_amount_positive"),
        _currency_check("tx_currency"),
    )


class Order(Timestamped, Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100))
    from_asset_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("assets.asset_id"), index=True
    )
    order_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action: Mapped[OrderAction] = mapped_column(_enum(OrderAction, "action"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
        ),
        Index("ix_orders_account", "from_account_id", "from_broker_id"),
    )


class Trade(Timestamped, Base):
    __tablename__ = "trades"

    trade_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_order_id: Mapped[str] = mapped_column(String(100))
    trade_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trade_amount: Mapped[Decimal] = mapped_column(Amount)
    trade_quantity: Mapped[Decimal] = mapped_column(Amount)
    trade_price: Mapped[Decimal] = mapped_column(Amount)
    trade_currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_order_id", "from_broker_id"],
            ["orders.order_id", "orders.from_broker_id"],
        ),
        Index("ix_trades_order", "from_order_id", "from_broker_id"),
        CheckConstraint("trade_amount >= 0", name="trade_amount_non_negative"),
        CheckConstraint("trade_quantity > 0", name="trade_quantity_positive"),
        CheckConstraint("trade_price >= 0", name="trade_price_non_negative"),
        _currency_check("trade_currency"),
    )


class Fee(Timestamped, Base):
    __tablename__ = "fees"

    from_trade_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    fee_type: Mapped[FeeType] = mapped_column(
        _enum(FeeType, "fee_type"), primary_key=True
    )
    fee_amount: Mapped[Decimal] = mapped_column(Amount)
    fee_currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_trade_id", "from_broker_id"],
            ["trades.trade_id", "trades.from_broker_id"],
        ),
        CheckConstraint("fee_amount > 0", name="fee_amount_positive"),
        _currency_check("fee_currency"),
    )
