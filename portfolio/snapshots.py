from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from database.models import (
    Account,
    BrokerAsset,
    CanonicalAsset,
    CashSnapshot,
    ListingCategory,
    PositionSnapshot,
    SnapshotDay,
)


@dataclass(frozen=True)
class Holding:
    asset_id: str
    ticker: str
    category: ListingCategory
    exchange: str
    quantity: Decimal
    cost_basis: Decimal
    currency: str


@dataclass(frozen=True)
class AccountSnapshot:
    broker_id: str
    account_id: str
    snapshot_date: date
    holdings: tuple[Holding, ...] = ()
    cash: dict[str, Decimal] = field(default_factory=dict)
    included: bool = True


Key = tuple[date, str, str]


def load_snapshots(session: Session, user_id: str) -> list[AccountSnapshot]:
    account = and_(
        Account.account_id == PositionSnapshot.from_account_id,
        Account.from_broker_id == PositionSnapshot.from_broker_id,
    )
    broker_asset = and_(
        BrokerAsset.broker_asset_id == PositionSnapshot.from_broker_asset_id,
        BrokerAsset.from_broker_id == PositionSnapshot.from_broker_id,
    )

    positions = session.execute(
        select(PositionSnapshot, CanonicalAsset)
        .join(Account, account)
        .join(BrokerAsset, broker_asset)
        .join(
            CanonicalAsset,
            CanonicalAsset.trading_venue_figi == BrokerAsset.from_asset_id,
        )
        .where(Account.from_user_id == user_id, Account.included)
    ).all()

    cash = session.scalars(
        select(CashSnapshot)
        .join(
            Account,
            and_(
                Account.account_id == CashSnapshot.from_account_id,
                Account.from_broker_id == CashSnapshot.from_broker_id,
            ),
        )
        .where(Account.from_user_id == user_id, Account.included)
    ).all()

    days = session.execute(
        select(SnapshotDay, Account.included)
        .join(
            Account,
            and_(
                Account.account_id == SnapshotDay.from_account_id,
                Account.from_broker_id == SnapshotDay.from_broker_id,
            ),
        )
        .where(Account.from_user_id == user_id)
    ).all()
    synced: dict[Key, bool] = {
        (row.snapshot_date, row.from_broker_id, row.from_account_id): included
        for row, included in days
    }

    holdings: dict[Key, list[Holding]] = defaultdict(list)
    for row, asset in positions:
        key = (row.snapshot_date, row.from_broker_id, row.from_account_id)
        holdings[key].append(
            Holding(
                asset_id=asset.trading_venue_figi,
                ticker=asset.ticker,
                category=asset.listing_category,
                exchange=asset.listing_exchange,
                quantity=row.quantity,
                cost_basis=row.cost_basis,
                currency=row.currency,
            )
        )

    balances: dict[Key, dict[str, Decimal]] = defaultdict(dict)
    for row in cash:
        key = (row.snapshot_date, row.from_broker_id, row.from_account_id)
        balances[key][row.currency] = row.balance

    snapshots = []
    for key in sorted(synced | holdings.keys() | balances.keys()):
        day, broker_id, account_id = key
        snapshots.append(
            AccountSnapshot(
                broker_id=broker_id,
                account_id=account_id,
                snapshot_date=day,
                holdings=tuple(sorted(holdings.get(key, ()), key=lambda h: h.asset_id)),
                cash=balances.get(key, {}),
                included=synced.get(key, True),
            )
        )
    return snapshots
