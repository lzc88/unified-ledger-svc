import base64
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Literal, get_args

from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.models import ExecutedCash
from portfolio.records import (
    EntryKind,
    EntryRef,
    FxRecord,
    TradeRecord,
    records_page,
)

OrderKey = tuple[str, str]
EntryKey = tuple[str, str, str]


class InvalidCursorError(ValueError):
    pass


class Fill(BaseModel):
    fill_id: str
    at: datetime
    quantity: float
    price: float
    amount: float


class Fee(BaseModel):
    fill_id: str
    fee_type: str
    amount: float
    currency: str


class LedgerEntry(BaseModel):
    """One order (its fills summed) or one cash movement.

    Amounts are unsigned; `action` gives the direction. For FX, `quantity` is in
    `base_currency` and `price` and `amount` are in `currency`.
    """

    kind: Literal["TRADE", "FX", "CASH"]
    entry_id: str
    broker_id: str
    account_id: str
    at: datetime
    action: str
    symbol: str | None
    asset_id: str | None
    category: str | None
    exchange: str | None
    base_currency: str | None
    currency: str
    quantity: float | None
    price: float | None
    amount: float
    fills: list[Fill]
    fees: list[Fee]


class LedgerActivity(BaseModel):
    """One page of entries, newest first.

    `total` counts every entry matching the filters; `next_cursor` fetches the
    page after this one and is null on the last page.
    """

    user_id: str
    entries: list[LedgerEntry]
    total: int
    next_cursor: str | None


def ledger_page(
    session: Session,
    user_id: str,
    *,
    limit: int,
    cursor: str | None = None,
    kind: EntryKind | None = None,
    asset_id: str | None = None,
) -> LedgerActivity:
    page = records_page(
        session,
        user_id,
        limit=limit,
        after=decode_cursor(cursor) if cursor else None,
        kind=kind,
        asset_id=asset_id,
    )

    built: dict[EntryKey, LedgerEntry] = {
        (e.kind, e.broker_id, e.entry_id): e
        for e in [
            *_trade_orders(page.records.trades),
            *_fx_orders(page.records.fx),
            *(_cash(row) for row in page.records.cash),
        ]
    }

    return LedgerActivity(
        user_id=user_id,
        entries=[built[(r.kind, r.broker_id, r.entry_id)] for r in page.refs],
        total=page.total,
        next_cursor=encode_cursor(page.refs[-1]) if page.has_more else None,
    )


def encode_cursor(ref: EntryRef) -> str:
    raw = json.dumps([ref.at.isoformat(), ref.entry_id, ref.kind, ref.broker_id])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> EntryRef:
    try:
        at, entry_id, kind, broker_id = json.loads(base64.urlsafe_b64decode(cursor))
        ref = EntryRef(datetime.fromisoformat(at), entry_id, kind, broker_id)
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError("invalid cursor") from exc

    if (
        ref.kind not in get_args(EntryKind)
        or ref.at.tzinfo is None
        or not isinstance(ref.entry_id, str)
        or not isinstance(ref.broker_id, str)
    ):
        raise InvalidCursorError("invalid cursor")
    return ref


def _summed(quantities: list[Decimal], amounts: list[Decimal]):
    quantity = sum(quantities, Decimal(0))
    amount = sum(amounts, Decimal(0))
    price = amount / quantity if quantity else None
    return quantity, price, amount


def _trade_orders(records: list[TradeRecord]) -> list[LedgerEntry]:
    groups: defaultdict[OrderKey, list[TradeRecord]] = defaultdict(list)
    for record in records:
        groups[(record.order.trade_order_id, record.order.from_broker_id)].append(
            record
        )

    entries = []
    for group in groups.values():
        group = sorted(group, key=lambda r: (r.trade.trade_datetime, r.trade.trade_id))
        order, asset = group[0].order, group[0].asset
        trades = [r.trade for r in group]
        quantity, price, amount = _summed(
            [t.trade_quantity for t in trades], [t.trade_amount for t in trades]
        )

        entries.append(
            LedgerEntry(
                kind="TRADE",
                entry_id=order.trade_order_id,
                broker_id=order.from_broker_id,
                account_id=order.from_account_id,
                at=order.order_datetime,
                action=order.action,
                symbol=asset.ticker,
                asset_id=asset.trading_venue_figi,
                category=asset.listing_category,
                exchange=asset.listing_exchange,
                base_currency=None,
                currency=trades[0].trade_currency,
                quantity=quantity,
                price=price,
                amount=amount,
                fills=[
                    Fill(
                        fill_id=t.trade_id,
                        at=t.trade_datetime,
                        quantity=t.trade_quantity,
                        price=t.trade_price,
                        amount=t.trade_amount,
                    )
                    for t in trades
                ],
                fees=[
                    Fee(
                        fill_id=f.from_trade_id,
                        fee_type=f.trade_fee_type,
                        amount=f.trade_fee_amount,
                        currency=f.trade_fee_currency,
                    )
                    for r in group
                    for f in r.fees
                ],
            )
        )
    return entries


def _fx_orders(records: list[FxRecord]) -> list[LedgerEntry]:
    groups: defaultdict[OrderKey, list[FxRecord]] = defaultdict(list)
    for record in records:
        groups[(record.order.fx_order_id, record.order.from_broker_id)].append(record)

    entries = []
    for group in groups.values():
        group = sorted(group, key=lambda r: (r.fx.fx_datetime, r.fx.fx_id))
        order, pair = group[0].order, group[0].pair
        conversions = [r.fx for r in group]
        quantity, price, amount = _summed(
            [fx.fx_quantity for fx in conversions],
            [fx.fx_amount for fx in conversions],
        )

        entries.append(
            LedgerEntry(
                kind="FX",
                entry_id=order.fx_order_id,
                broker_id=order.from_broker_id,
                account_id=order.from_account_id,
                at=order.order_datetime,
                action=order.action,
                symbol=pair.fx_pair_id,
                asset_id=None,
                category=None,
                exchange=None,
                base_currency=pair.fx_long_currency,
                currency=pair.fx_short_currency,
                quantity=quantity,
                price=price,
                amount=amount,
                fills=[
                    Fill(
                        fill_id=fx.fx_id,
                        at=fx.fx_datetime,
                        quantity=fx.fx_quantity,
                        price=fx.fx_price,
                        amount=fx.fx_amount,
                    )
                    for fx in conversions
                ],
                fees=[
                    Fee(
                        fill_id=f.from_fx_id,
                        fee_type=f.fx_fee_type,
                        amount=f.fx_fee_amount,
                        currency=f.fx_fee_currency,
                    )
                    for r in group
                    for f in r.fees
                ],
            )
        )
    return entries


def _cash(row: ExecutedCash) -> LedgerEntry:
    return LedgerEntry(
        kind="CASH",
        entry_id=row.cash_id,
        broker_id=row.from_broker_id,
        account_id=row.from_account_id,
        at=row.tx_datetime,
        action=row.action,
        symbol=None,
        asset_id=None,
        category=None,
        exchange=None,
        base_currency=None,
        currency=row.tx_currency,
        quantity=None,
        price=None,
        amount=row.tx_amount,
        fills=[],
        fees=[],
    )
