from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    ColumnElement,
    Select,
    String,
    func,
    literal_column,
    select,
    tuple_,
    union_all,
)
from sqlalchemy.orm import Session

from database.models import (
    Account,
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
)

RowKey = tuple[str, str]
EntryKind = Literal["TRADE", "FX", "CASH"]


@dataclass(frozen=True)
class TradeRecord:
    trade: ExecutedTrade
    order: ExecutedTradeOrder
    asset: CanonicalAsset
    fees: tuple[TradeFee, ...]


@dataclass(frozen=True)
class FxRecord:
    fx: ExecutedFx
    order: ExecutedFxOrder
    pair: CanonicalFx
    fees: tuple[FxFee, ...]


@dataclass(frozen=True)
class UserRecords:
    cash: list[ExecutedCash]
    trades: list[TradeRecord]
    fx: list[FxRecord]


@dataclass(frozen=True)
class EntryRef:
    at: datetime
    entry_id: str
    kind: EntryKind
    broker_id: str


@dataclass(frozen=True)
class RecordsPage:
    refs: list[EntryRef]
    records: UserRecords
    total: int
    has_more: bool


def user_records(session: Session, user_id: str) -> UserRecords:
    accounts = _accounts_of(user_id)
    return UserRecords(
        cash=_cash(session, _cash_of(accounts)),
        trades=_trades(session, _trade_orders_of(accounts)),
        fx=_fx(session, _fx_orders_of(accounts)),
    )


def records_page(
    session: Session,
    user_id: str,
    *,
    limit: int,
    after: EntryRef | None = None,
    kind: EntryKind | None = None,
    asset_id: str | None = None,
) -> RecordsPage:
    """One page of the user's orders and cash movements, newest first.

    Entries are ordered by (at, entry_id, kind, broker_id), descending; `after`
    continues from the last entry of the previous page.
    """
    parts = _entry_refs(_accounts_of(user_id), kind, asset_id)
    if not parts:
        return RecordsPage([], UserRecords([], [], []), 0, False)

    entries = (union_all(*parts) if len(parts) > 1 else parts[0]).subquery()
    total = session.scalar(select(func.count()).select_from(entries)) or 0

    query = (
        select(entries.c.at, entries.c.entry_id, entries.c.kind, entries.c.broker_id)
        .order_by(
            entries.c.at.desc(),
            entries.c.entry_id.desc(),
            entries.c.kind.desc(),
            entries.c.broker_id.desc(),
        )
        .limit(limit + 1)
    )
    if after is not None:
        query = query.where(
            tuple_(entries.c.at, entries.c.entry_id, entries.c.kind, entries.c.broker_id)
            < tuple_(after.at, after.entry_id, after.kind, after.broker_id)
        )

    refs = [EntryRef(*row) for row in session.execute(query).all()]
    has_more = len(refs) > limit
    refs = refs[:limit]

    return RecordsPage(
        refs=refs,
        records=_records_for(session, refs),
        total=total,
        has_more=has_more,
    )


_ORDER_OF_TRADE = (
    ExecutedTradeOrder.trade_order_id == ExecutedTrade.from_trade_order_id
) & (ExecutedTradeOrder.from_broker_id == ExecutedTrade.from_broker_id)

_ORDER_OF_FX = (ExecutedFxOrder.fx_order_id == ExecutedFx.from_fx_order_id) & (
    ExecutedFxOrder.from_broker_id == ExecutedFx.from_broker_id
)

_ASSET_OF_ORDER = (
    BrokerAsset.broker_asset_id == ExecutedTradeOrder.from_broker_asset_id
) & (BrokerAsset.from_broker_id == ExecutedTradeOrder.from_broker_id)


def _accounts_of(user_id: str) -> Select:
    return select(Account.account_id, Account.from_broker_id).where(
        Account.from_user_id == user_id
    )


def _trade_orders_of(accounts: Select) -> ColumnElement[bool]:
    return tuple_(
        ExecutedTradeOrder.from_account_id, ExecutedTradeOrder.from_broker_id
    ).in_(accounts)


def _fx_orders_of(accounts: Select) -> ColumnElement[bool]:
    return tuple_(ExecutedFxOrder.from_account_id, ExecutedFxOrder.from_broker_id).in_(
        accounts
    )


def _cash_of(accounts: Select) -> ColumnElement[bool]:
    return tuple_(ExecutedCash.from_account_id, ExecutedCash.from_broker_id).in_(
        accounts
    )


def _kind(value: str):
    return literal_column(f"'{value}'", String).label("kind")


def _entry_refs(
    accounts: Select, kind: EntryKind | None, asset_id: str | None
) -> list[Select]:
    parts = []

    if kind in (None, "TRADE"):
        trades = select(
            ExecutedTradeOrder.order_datetime.label("at"),
            ExecutedTradeOrder.trade_order_id.label("entry_id"),
            _kind("TRADE"),
            ExecutedTradeOrder.from_broker_id.label("broker_id"),
        ).where(
            _trade_orders_of(accounts),
            select(ExecutedTrade.trade_id).where(_ORDER_OF_TRADE).exists(),
        )
        if asset_id is not None:
            trades = trades.join(BrokerAsset, _ASSET_OF_ORDER).where(
                BrokerAsset.from_asset_id == asset_id
            )
        parts.append(trades)

    if asset_id is None and kind in (None, "FX"):
        parts.append(
            select(
                ExecutedFxOrder.order_datetime.label("at"),
                ExecutedFxOrder.fx_order_id.label("entry_id"),
                _kind("FX"),
                ExecutedFxOrder.from_broker_id.label("broker_id"),
            ).where(
                _fx_orders_of(accounts),
                select(ExecutedFx.fx_id).where(_ORDER_OF_FX).exists(),
            )
        )

    if asset_id is None and kind in (None, "CASH"):
        parts.append(
            select(
                ExecutedCash.tx_datetime.label("at"),
                ExecutedCash.cash_id.label("entry_id"),
                _kind("CASH"),
                ExecutedCash.from_broker_id.label("broker_id"),
            ).where(_cash_of(accounts))
        )

    return parts


def _records_for(session: Session, refs: list[EntryRef]) -> UserRecords:
    keys: defaultdict[str, list[RowKey]] = defaultdict(list)
    for ref in refs:
        keys[ref.kind].append((ref.entry_id, ref.broker_id))

    cash, trades, fx = keys["CASH"], keys["TRADE"], keys["FX"]
    return UserRecords(
        cash=_cash(
            session,
            tuple_(ExecutedCash.cash_id, ExecutedCash.from_broker_id).in_(cash),
        )
        if cash
        else [],
        trades=_trades(
            session,
            tuple_(
                ExecutedTradeOrder.trade_order_id, ExecutedTradeOrder.from_broker_id
            ).in_(trades),
        )
        if trades
        else [],
        fx=_fx(
            session,
            tuple_(ExecutedFxOrder.fx_order_id, ExecutedFxOrder.from_broker_id).in_(fx),
        )
        if fx
        else [],
    )


def _cash(session: Session, where: ColumnElement[bool]) -> list[ExecutedCash]:
    return list(session.scalars(select(ExecutedCash).where(where)))


def _trades(session: Session, where: ColumnElement[bool]) -> list[TradeRecord]:
    rows = session.execute(
        select(ExecutedTrade, ExecutedTradeOrder, CanonicalAsset)
        .join(ExecutedTradeOrder, _ORDER_OF_TRADE)
        .join(BrokerAsset, _ASSET_OF_ORDER)
        .join(
            CanonicalAsset,
            CanonicalAsset.trading_venue_figi == BrokerAsset.from_asset_id,
        )
        .where(where)
    ).all()

    fees = _grouped(
        session.scalars(
            select(TradeFee)
            .join(
                ExecutedTrade,
                (ExecutedTrade.trade_id == TradeFee.from_trade_id)
                & (ExecutedTrade.from_broker_id == TradeFee.from_broker_id),
            )
            .join(ExecutedTradeOrder, _ORDER_OF_TRADE)
            .where(where)
        ),
        lambda fee: (fee.from_trade_id, fee.from_broker_id),
    )

    return [
        TradeRecord(
            trade=trade,
            order=order,
            asset=asset,
            fees=tuple(fees.get((trade.trade_id, trade.from_broker_id), ())),
        )
        for trade, order, asset in rows
    ]


def _fx(session: Session, where: ColumnElement[bool]) -> list[FxRecord]:
    rows = session.execute(
        select(ExecutedFx, ExecutedFxOrder, CanonicalFx)
        .join(ExecutedFxOrder, _ORDER_OF_FX)
        .join(CanonicalFx, CanonicalFx.fx_pair_id == ExecutedFxOrder.from_fx_pair_id)
        .where(where)
    ).all()

    fees = _grouped(
        session.scalars(
            select(FxFee)
            .join(
                ExecutedFx,
                (ExecutedFx.fx_id == FxFee.from_fx_id)
                & (ExecutedFx.from_broker_id == FxFee.from_broker_id),
            )
            .join(ExecutedFxOrder, _ORDER_OF_FX)
            .where(where)
        ),
        lambda fee: (fee.from_fx_id, fee.from_broker_id),
    )

    return [
        FxRecord(
            fx=fx,
            order=order,
            pair=pair,
            fees=tuple(fees.get((fx.fx_id, fx.from_broker_id), ())),
        )
        for fx, order, pair in rows
    ]


def _grouped(rows: Iterable, key) -> dict[RowKey, list]:
    grouped: defaultdict[RowKey, list] = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return grouped
