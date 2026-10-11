from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from database.models import CashAction, ListingCategory, OrderAction

ZERO = Decimal(0)

Fees = tuple[tuple[str, Decimal], ...]


class LedgerError(Exception):
    pass


@dataclass(frozen=True)
class CashFlow:
    at: datetime
    action: CashAction
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class Trade:
    at: datetime
    asset_id: str
    ticker: str
    category: ListingCategory
    exchange: str
    action: OrderAction
    quantity: Decimal
    amount: Decimal
    currency: str
    fees: Fees = ()


@dataclass(frozen=True)
class FxTrade:
    at: datetime
    pair_id: str
    long_currency: str
    short_currency: str
    action: OrderAction
    quantity: Decimal
    amount: Decimal
    fees: Fees = ()


Event = CashFlow | Trade | FxTrade


@dataclass
class Holding:
    asset_id: str
    ticker: str
    category: ListingCategory
    exchange: str
    currency: str
    quantity: Decimal = ZERO
    cost: Decimal = ZERO
    realised: Decimal = ZERO

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


def _balances() -> defaultdict[str, Decimal]:
    return defaultdict(Decimal)


@dataclass
class Book:
    cash: defaultdict[str, Decimal] = field(default_factory=_balances)
    deposits: defaultdict[str, Decimal] = field(default_factory=_balances)
    withdrawals: defaultdict[str, Decimal] = field(default_factory=_balances)
    fees: defaultdict[str, Decimal] = field(default_factory=_balances)
    holdings: dict[str, Holding] = field(default_factory=dict)


@dataclass(frozen=True)
class Snapshot:
    month: date
    cash: dict[str, Decimal]
    net_capital: dict[str, Decimal]
    quantities: dict[str, Decimal]


def replay(events: Iterable[Event]) -> tuple[Book, list[Snapshot]]:
    book = Book()
    snapshots: list[Snapshot] = []
    month: date | None = None
    for event in sorted(events, key=lambda e: e.at):
        event_month = event.at.date().replace(day=1)
        if month is not None and event_month != month:
            snapshots.append(_snapshot(book, month))
        month = event_month
        match event:
            case CashFlow():
                _apply_cash(book, event)
            case Trade():
                _apply_trade(book, event)
            case FxTrade():
                _apply_fx(book, event)
    if month is not None:
        snapshots.append(_snapshot(book, month))
    return book, snapshots


def _apply_cash(book: Book, flow: CashFlow) -> None:
    if flow.action is CashAction.DEPOSIT:
        book.cash[flow.currency] += flow.amount
        book.deposits[flow.currency] += flow.amount
    else:
        book.cash[flow.currency] -= flow.amount
        book.withdrawals[flow.currency] += flow.amount


def _apply_fees(book: Book, fees: Fees) -> None:
    for currency, amount in fees:
        book.cash[currency] -= amount
        book.fees[currency] += amount


def _apply_fx(book: Book, fx: FxTrade) -> None:
    _apply_fees(book, fx.fees)
    sign = 1 if fx.action is OrderAction.BUY else -1
    book.cash[fx.long_currency] += sign * fx.quantity
    book.cash[fx.short_currency] -= sign * fx.amount


def _apply_trade(book: Book, trade: Trade) -> None:
    _apply_fees(book, trade.fees)
    holding = book.holdings.setdefault(
        trade.asset_id,
        Holding(
            trade.asset_id,
            trade.ticker,
            trade.category,
            trade.exchange,
            trade.currency,
        ),
    )
    if holding.currency != trade.currency:
        raise LedgerError(
            f"{trade.asset_id} trades in both {holding.currency} and {trade.currency}"
        )
    same_currency_fees = sum((a for c, a in trade.fees if c == trade.currency), ZERO)
    if trade.action is OrderAction.BUY:
        book.cash[trade.currency] -= trade.amount
        holding.quantity += trade.quantity
        holding.cost += trade.amount + same_currency_fees
        return

    if trade.quantity > holding.quantity:
        raise LedgerError(
            f"sell of {trade.quantity} {trade.asset_id} on {trade.at:%Y-%m-%d} exceeds "
            f"the {holding.quantity} held; short positions are not supported"
        )
    book.cash[trade.currency] += trade.amount
    released_cost = holding.cost * trade.quantity / holding.quantity
    holding.realised += trade.amount - same_currency_fees - released_cost
    holding.cost -= released_cost
    holding.quantity -= trade.quantity
    if holding.quantity == 0:
        holding.cost = ZERO


def _snapshot(book: Book, month: date) -> Snapshot:
    currencies = set(book.deposits) | set(book.withdrawals)
    return Snapshot(
        month=month,
        cash=dict(book.cash),
        net_capital={c: book.deposits[c] - book.withdrawals[c] for c in currencies},
        quantities={a: h.quantity for a, h in book.holdings.items() if h.is_open},
    )
