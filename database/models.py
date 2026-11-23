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


class SyncStatus(enum.StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


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
    rates: Mapped[dict[str, float]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )

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
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[SyncStatus | None] = mapped_column(
        _enum(SyncStatus, "last_sync_status")
    )
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    last_sync_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


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


class SnapshotDay(Timestamped, Base):
    __tablename__ = "account_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_account_snapshots_account_date",
            "from_account_id",
            "from_broker_id",
            "snapshot_date",
        ),
    )


class PositionSnapshot(Timestamped, Base):
    __tablename__ = "position_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_broker_asset_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Amount)
    cost_basis: Mapped[Decimal] = mapped_column(Amount)
    currency: Mapped[str] = mapped_column(CHAR(3))

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["from_broker_asset_id", "from_broker_id"],
            ["broker_assets.broker_asset_id", "broker_assets.from_broker_id"],
        ),
        Index(
            "ix_position_snapshots_account_date",
            "from_account_id",
            "from_broker_id",
            "snapshot_date",
        ),
        CheckConstraint("quantity <> 0", name="quantity_non_zero"),
        _currency_check("currency"),
    )


class CashSnapshot(Timestamped, Base):
    __tablename__ = "cash_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    from_broker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    from_account_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    currency: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    balance: Mapped[Decimal] = mapped_column(Amount)

    __table_args__ = (
        ForeignKeyConstraint(
            ["from_account_id", "from_broker_id"],
            ["accounts.account_id", "accounts.from_broker_id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_cash_snapshots_account_date",
            "from_account_id",
            "from_broker_id",
            "snapshot_date",
        ),
        _currency_check("currency"),
    )
