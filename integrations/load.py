from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.db import Base
from database.models import (
    Account,
    Broker,
    BrokerAsset,
    CanonicalAsset,
    CanonicalFx,
    ExecutedCash,
    ExecutedFx,
    ExecutedFxOrder,
    ExecutedTrade,
    ExecutedTradeOrder,
    FxFee,
    TradeFee,
    User,
)

from .base import BrokerAdapter, MappingResult, Row


def load(
    session: Session, broker: BrokerAdapter, result: MappingResult, user_id: str
) -> dict[str, int]:
    broker_id = broker.broker_id
    user_name = next(iter(result.account_names.values()), user_id)
    inserted = {
        "brokers": _insert_new(
            session,
            Broker,
            [{"broker_id": broker_id, "broker_name": broker.broker_name}],
        ),
        "users": _upsert_user(session, user_id, user_name),
    }

    def stamp(rows: dict) -> list[Row]:
        return [{**row, "from_broker_id": broker_id} for row in rows.values()]

    new_assets = {
        broker_asset_id: row
        for broker_asset_id, row in result.assets.items()
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
    accounts = [{**row, "from_user_id": user_id} for row in stamp(result.accounts)]
    batches: list[tuple[type[Base], list[Row]]] = [
        (CanonicalAsset, canonical_assets),
        (BrokerAsset, broker_assets),
        (Account, accounts),
        (ExecutedCash, stamp(result.cash)),
        (ExecutedTradeOrder, stamp(result.trade_orders)),
        (ExecutedTrade, stamp(result.trades)),
        (TradeFee, stamp(result.trade_fees)),
        (CanonicalFx, list(result.fx_pairs.values())),
        (ExecutedFxOrder, stamp(result.fx_orders)),
        (ExecutedFx, stamp(result.fx)),
        (FxFee, stamp(result.fx_fees)),
    ]
    for model, rows in batches:
        inserted[model.__tablename__] = _insert_new(session, model, rows)
    return inserted


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


def _upsert_user(session: Session, user_id: str, user_name: str) -> int:
    statement = insert(User).values(user_id=user_id, user_name=user_name)
    statement = statement.on_conflict_do_update(
        index_elements=[User.user_id],
        set_={"user_name": statement.excluded.user_name, "updated_at": func.now()},
        where=User.user_name == User.user_id,
    ).returning(User.user_id)
    return len(session.scalars(statement).all())


def _insert_new(session: Session, model: type[Base], rows: list[Row]) -> int:
    if not rows:
        return 0
    key = model.__table__.primary_key.columns[0]
    statement = insert(model).on_conflict_do_nothing().returning(key)
    return len(session.scalars(statement, rows).all())
