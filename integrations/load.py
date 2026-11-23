from collections.abc import Iterable
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.db import Base
from database.models import (
    Account,
    Broker,
    BrokerAsset,
    CanonicalAsset,
    CashSnapshot,
    PositionSnapshot,
    SnapshotDay,
)

from .base import BrokerAdapter, IntegrationError, Row, Snapshot


def store_snapshot(
    session: Session,
    broker: BrokerAdapter,
    snapshot: Snapshot,
    user_id: str,
    snapshot_date: date,
) -> dict[str, int]:
    broker_id = broker.broker_id
    if not snapshot.accounts:
        raise IntegrationError(
            f"{broker_id} returned no accounts; nothing was stored"
        )

    counts = {
        "brokers": _insert_new(
            session,
            Broker,
            [{"broker_id": broker_id, "broker_name": broker.broker_name}],
        ),
    }

    new_assets = {
        broker_asset_id: row
        for broker_asset_id, row in snapshot.assets.items()
        if "trading_venue_figi" in row
    }
    canonical_assets = list(
        {row["trading_venue_figi"]: row for row in new_assets.values()}.values()
    )
    broker_assets = [
        {
            "broker_asset_id": broker_asset_id,
            "from_broker_id": broker_id,
            "from_asset_id": row["trading_venue_figi"],
        }
        for broker_asset_id, row in new_assets.items()
    ]
    accounts = [
        {**row, "from_broker_id": broker_id, "from_user_id": user_id}
        for row in snapshot.accounts.values()
    ]

    batches: list[tuple[type[Base], list[Row]]] = [
        (CanonicalAsset, canonical_assets),
        (BrokerAsset, broker_assets),
        (Account, accounts),
    ]
    for model, rows in batches:
        counts[model.__tablename__] = _insert_new(session, model, rows)

    _ensure_owned(session, broker_id, user_id, snapshot.accounts)

    user_accounts = select(Account.account_id).where(
        Account.from_user_id == user_id, Account.from_broker_id == broker_id
    )
    for model in (SnapshotDay, PositionSnapshot, CashSnapshot):
        session.execute(
            delete(model)
            .where(
                model.snapshot_date == snapshot_date,
                model.from_broker_id == broker_id,
                model.from_account_id.in_(user_accounts),
            )
            .execution_options(synchronize_session=False)
        )

    def stamp(rows: dict) -> list[Row]:
        return [
            {**row, "snapshot_date": snapshot_date, "from_broker_id": broker_id}
            for row in rows.values()
        ]

    counts[SnapshotDay.__tablename__] = _insert_all(
        session,
        SnapshotDay,
        [
            {
                "snapshot_date": snapshot_date,
                "from_broker_id": broker_id,
                "from_account_id": account_id,
            }
            for account_id in snapshot.accounts
        ],
    )
    counts[PositionSnapshot.__tablename__] = _insert_all(
        session, PositionSnapshot, stamp(snapshot.positions)
    )
    counts[CashSnapshot.__tablename__] = _insert_all(
        session, CashSnapshot, stamp(snapshot.cash)
    )

    return counts


def known_broker_assets(
    session: Session, broker_id: str, broker_asset_ids: Iterable[str]
) -> set[str]:
    ids = list(broker_asset_ids)
    if not ids:
        return set()
    return set(
        session.scalars(
            select(BrokerAsset.broker_asset_id).where(
                BrokerAsset.from_broker_id == broker_id,
                BrokerAsset.broker_asset_id.in_(ids),
            )
        )
    )


def _ensure_owned(
    session: Session, broker_id: str, user_id: str, account_ids: Iterable[str]
) -> None:
    ids = list(account_ids)
    if not ids:
        return

    foreign = session.scalars(
        select(Account.account_id).where(
            Account.from_broker_id == broker_id,
            Account.account_id.in_(ids),
            Account.from_user_id != user_id,
        )
    ).first()
    if foreign is not None:
        raise IntegrationError(
            f"{broker_id} account {foreign} is linked to another user"
        )


def _insert_new(session: Session, model: type[Base], rows: list[Row]) -> int:
    if not rows:
        return 0
    key = model.__table__.primary_key.columns[0]
    statement = insert(model).on_conflict_do_nothing().returning(key)
    return len(session.scalars(statement, rows).all())


def _insert_all(session: Session, model: type[Base], rows: list[Row]) -> int:
    if not rows:
        return 0
    session.execute(insert(model), rows)
    return len(rows)
