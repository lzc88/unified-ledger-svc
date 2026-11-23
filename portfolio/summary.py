from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel

from config.config import PORTFOLIO_DUST, PORTFOLIO_HISTORY_LOOKBACK_DAYS
from database.models import ListingCategory

from .market import MarketData, MarketDataError, Quote, fx_symbol, yahoo_symbol
from .snapshots import AccountSnapshot, Holding

ZERO = Decimal(0)


class NoSnapshotsError(Exception):
    pass


class Position(BaseModel):
    asset_id: str
    symbol: str
    yahoo_symbol: str | None
    category: str
    exchange: str
    currency: str
    brokers: list[str]
    quantity: float
    avg_cost: float | None
    cost_basis: float | None
    price: float | None
    market_value: float | None
    unrealised: float | None


class CashBalance(BaseModel):
    broker_id: str
    currency: str
    amount: float
    value: float | None


class Totals(BaseModel):
    value: float | None
    cash: float | None
    market_value: float | None
    cost_basis: float | None
    unrealised: float | None


class HistoryPoint(BaseModel):
    date: date
    value: float | None


class PortfolioSummary(BaseModel):
    user_id: str
    currency: str
    as_of: datetime
    snapshot_date: date
    fx_rates: dict[str, float]
    totals: Totals
    positions: list[Position]
    cash: list[CashBalance]
    history: list[HistoryPoint]
    warnings: list[str]


Rate = Decimal | None
AccountKey = tuple[str, str]
Closes = dict[str, tuple[list[date], list[Decimal]]]


@dataclass(frozen=True)
class Asset:
    asset_id: str
    ticker: str
    category: ListingCategory
    exchange: str
    currency: str


@dataclass
class Merged:
    asset: Asset
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    brokers: set[str] = field(default_factory=set)
    currencies: set[str] = field(default_factory=set)
    costs: dict[str, Decimal] = field(default_factory=dict)


def build_summary(
    user_id: str,
    snapshots: Sequence[AccountSnapshot],
    market: MarketData,
    currency: str,
    today: date,
) -> PortfolioSummary:
    if not snapshots:
        raise NoSnapshotsError(f"no broker snapshots for user {user_id!r}")

    warnings: list[str] = []
    ordered = sorted(snapshots, key=lambda s: (s.snapshot_date, s.broker_id, s.account_id))
    latest = _latest(ordered)
    snapshot_date = max(s.snapshot_date for s in latest.values())
    _warn_stale(latest, snapshot_date, warnings)

    merged = _merge(latest.values(), warnings)
    assets = _assets(ordered, merged)
    symbols = _yahoo_symbols(assets, warnings)

    cash_currencies = {c for s in ordered for c in s.cash}
    cost_currencies = {c for m in merged.values() for c in m.costs}
    foreign = (
        cash_currencies | cost_currencies | {a.currency for a in assets.values()}
    ) - {currency}
    fx_symbols = {c: fx_symbol(c, currency) for c in foreign}

    quotes = market.quotes(set(symbols.values()) | set(fx_symbols.values()))
    priceable = _priceable(assets, symbols, quotes, warnings)
    fx = _live_fx(currency, fx_symbols, quotes, warnings)
    prices = {a: _price(priceable.get(a), quotes, warnings) for a in merged}

    market_value = _sum(
        _mul(m.quantity, prices[a], fx.get(m.asset.currency)) for a, m in merged.items()
    )
    costs = {a: _cost(m, fx) for a, m in merged.items()}
    cost_basis = _sum(_mul(costs[a], fx.get(m.asset.currency)) for a, m in merged.items())
    amounts = _cash_amounts(latest.values())
    cash_value = _sum(_mul(a, fx.get(c)) for (_, c), a in amounts.items())
    value = _add(cash_value, market_value)

    totals = Totals(
        value=_float(value),
        cash=_float(cash_value),
        market_value=_float(market_value),
        cost_basis=_float(cost_basis),
        unrealised=_float(_sub(market_value, cost_basis)),
    )

    positions = [
        _position(m, symbols.get(a), prices[a], costs[a]) for a, m in merged.items()
    ]
    converted = {
        a: _mul(m.quantity, prices[a], fx.get(m.asset.currency)) or ZERO
        for a, m in merged.items()
    }
    positions.sort(key=lambda p: (-converted[p.asset_id], p.symbol))

    history = _history(
        ordered,
        assets,
        priceable,
        fx_symbols,
        currency,
        market,
        max(today, snapshot_date),
        value,
        warnings,
    )

    return PortfolioSummary(
        user_id=user_id,
        currency=currency,
        as_of=datetime.now(UTC),
        snapshot_date=snapshot_date,
        fx_rates={c: float(r) for c, r in fx.items() if r is not None},
        totals=totals,
        positions=positions,
        cash=_balances(amounts, fx),
        history=history,
        warnings=warnings,
    )


def _latest(ordered: Sequence[AccountSnapshot]) -> dict[AccountKey, AccountSnapshot]:
    latest: dict[AccountKey, AccountSnapshot] = {}
    for snapshot in ordered:
        latest[(snapshot.broker_id, snapshot.account_id)] = snapshot
    return dict(sorted(latest.items()))


def _warn_stale(
    latest: dict[AccountKey, AccountSnapshot], snapshot_date: date, warnings: list[str]
) -> None:
    for (broker_id, account_id), snapshot in latest.items():
        if snapshot.snapshot_date < snapshot_date:
            warnings.append(
                f"{broker_id} account {account_id} was last snapshotted on "
                f"{snapshot.snapshot_date.isoformat()}"
            )


def _asset(holding: Holding) -> Asset:
    return Asset(
        asset_id=holding.asset_id,
        ticker=holding.ticker,
        category=holding.category,
        exchange=holding.exchange,
        currency=holding.currency,
    )


def _merge(
    latest: Iterable[AccountSnapshot], warnings: list[str]
) -> dict[str, Merged]:
    merged: dict[str, Merged] = {}
    for snapshot in latest:
        for holding in snapshot.holdings:
            entry = merged.setdefault(holding.asset_id, Merged(_asset(holding)))
            entry.quantity += holding.quantity
            entry.cost_basis += holding.cost_basis
            entry.brokers.add(snapshot.broker_id)
            entry.currencies.add(holding.currency)
            entry.costs[holding.currency] = (
                entry.costs.get(holding.currency, ZERO) + holding.cost_basis
            )

    for entry in merged.values():
        if len(entry.currencies) > 1:
            warnings.append(
                f"{entry.asset.ticker} is held in {', '.join(sorted(entry.currencies))} "
                f"across brokers; its cost basis is converted to {entry.asset.currency}"
            )

    return {a: m for a, m in sorted(merged.items()) if abs(m.quantity) >= PORTFOLIO_DUST}


def _assets(
    ordered: Sequence[AccountSnapshot], merged: dict[str, Merged]
) -> dict[str, Asset]:
    assets = {a: m.asset for a, m in merged.items()}
    for snapshot in ordered:
        for holding in snapshot.holdings:
            assets.setdefault(holding.asset_id, _asset(holding))
    return dict(sorted(assets.items()))


def _yahoo_symbols(assets: dict[str, Asset], warnings: list[str]) -> dict[str, str]:
    symbols = {}
    for asset_id, asset in assets.items():
        symbol = yahoo_symbol(asset.ticker, asset.exchange)
        if symbol is None:
            warnings.append(f"no Yahoo exchange for {asset.ticker} on {asset.exchange}")
        else:
            symbols[asset_id] = symbol
    return symbols


def _priceable(
    assets: dict[str, Asset],
    symbols: dict[str, str],
    quotes: dict[str, Quote],
    warnings: list[str],
) -> dict[str, str]:
    priceable = {}
    for asset_id, symbol in symbols.items():
        quote, currency = quotes.get(symbol), assets[asset_id].currency
        if quote is not None and quote.currency != currency:
            warnings.append(
                f"{symbol} is quoted in {quote.currency} but trades in "
                f"{currency}, so it is left unpriced"
            )
        else:
            priceable[asset_id] = symbol
    return priceable


def _live_fx(
    currency: str,
    fx_symbols: dict[str, str],
    quotes: dict[str, Quote],
    warnings: list[str],
) -> dict[str, Rate]:
    fx: dict[str, Rate] = {currency: Decimal(1)}
    for c, s in sorted(fx_symbols.items()):
        fx[c] = quotes[s].price if s in quotes else None
        if fx[c] is None:
            warnings.append(
                f"no {c}/{currency} rate from Yahoo ({s}); {c} amounts are unconverted"
            )
    return fx


def _price(symbol: str | None, quotes: dict[str, Quote], warnings: list[str]) -> Rate:
    if symbol is None:
        return None

    quote = quotes.get(symbol)
    if quote is None:
        warnings.append(f"no live price from Yahoo for {symbol}")
        return None

    return quote.price


def _cost(m: Merged, fx: dict[str, Rate]) -> Rate:
    if set(m.costs) <= {m.asset.currency}:
        return m.cost_basis

    total = _sum(_mul(amount, fx.get(c)) for c, amount in m.costs.items())
    rate = fx.get(m.asset.currency)
    if total is None or not rate:
        return None
    return total / rate


def _position(m: Merged, symbol: str | None, price: Rate, cost: Rate) -> Position:
    value = _mul(m.quantity, price)
    return Position(
        asset_id=m.asset.asset_id,
        symbol=m.asset.ticker,
        yahoo_symbol=symbol,
        category=m.asset.category.value,
        exchange=m.asset.exchange,
        currency=m.asset.currency,
        brokers=sorted(m.brokers),
        quantity=float(m.quantity),
        avg_cost=None if cost is None else float(cost / m.quantity),
        cost_basis=_float(cost),
        price=_float(price),
        market_value=_float(value),
        unrealised=_float(_sub(value, cost)),
    )


def _cash_amounts(latest: Iterable[AccountSnapshot]) -> dict[tuple[str, str], Decimal]:
    amounts: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    for snapshot in latest:
        for c, balance in snapshot.cash.items():
            amounts[(snapshot.broker_id, c)] += balance
    return amounts


def _balances(
    amounts: dict[tuple[str, str], Decimal], fx: dict[str, Rate]
) -> list[CashBalance]:
    return [
        CashBalance(
            broker_id=broker_id,
            currency=c,
            amount=float(amount),
            value=_float(_mul(amount, fx.get(c))),
        )
        for (broker_id, c), amount in sorted(amounts.items())
        if abs(amount) >= PORTFOLIO_DUST
    ]


def _history(
    ordered: Sequence[AccountSnapshot],
    assets: dict[str, Asset],
    priceable: dict[str, str],
    fx_symbols: dict[str, str],
    currency: str,
    market: MarketData,
    end: date,
    live_value: Rate,
    warnings: list[str],
) -> list[HistoryPoint]:
    start = ordered[0].snapshot_date
    closes = _closes(
        market,
        set(priceable.values()) | set(fx_symbols.values()),
        start,
        end,
        warnings,
    )

    by_date: dict[date, list[AccountSnapshot]] = defaultdict(list)
    for snapshot in ordered:
        by_date[snapshot.snapshot_date].append(snapshot)

    state: dict[AccountKey, AccountSnapshot] = {}
    points = []
    day = start
    while day <= end:
        for snapshot in by_date.get(day, ()):
            state[(snapshot.broker_id, snapshot.account_id)] = snapshot

        if day == end:
            value = live_value
        else:
            value = _day_value(
                state.values(), assets, priceable, fx_symbols, currency, closes, day
            )

        points.append(HistoryPoint(date=day, value=_float(value)))
        day += timedelta(days=1)

    return points


def _closes(
    market: MarketData,
    symbols: set[str],
    start: date,
    end: date,
    warnings: list[str],
) -> Closes:
    if not symbols or start >= end:
        return {}

    lookback = start - timedelta(days=PORTFOLIO_HISTORY_LOOKBACK_DAYS)
    try:
        raw = market.daily_closes(symbols, lookback)
    except MarketDataError as exc:
        warnings.append(f"history is unpriced: {exc}")
        return {}

    closes = {}
    for symbol, series in raw.items():
        days = sorted(series)
        closes[symbol] = (days, [series[d] for d in days])
    return closes


def _close_on(closes: Closes, symbol: str | None, day: date) -> Rate:
    if symbol is None or symbol not in closes:
        return None

    days, values = closes[symbol]
    index = bisect_right(days, day)
    return values[index - 1] if index else None


def _day_value(
    state: Iterable[AccountSnapshot],
    assets: dict[str, Asset],
    priceable: dict[str, str],
    fx_symbols: dict[str, str],
    currency: str,
    closes: Closes,
    day: date,
) -> Rate:
    def rate(c: str) -> Rate:
        return Decimal(1) if c == currency else _close_on(closes, fx_symbols[c], day)

    total = ZERO
    for snapshot in state:
        for holding in snapshot.holdings:
            asset = assets[holding.asset_id]
            price = _close_on(closes, priceable.get(holding.asset_id), day)
            value = _mul(holding.quantity, price, rate(asset.currency))
            if value is None:
                return None
            total += value

        for c, balance in snapshot.cash.items():
            value = _mul(balance, rate(c))
            if value is None:
                return None
            total += value

    return total


def _mul(*values: Rate) -> Rate:
    result = Decimal(1)
    for v in values:
        if v is None:
            return None
        result *= v
    return result


def _add(a: Rate, b: Rate) -> Rate:
    return None if a is None or b is None else a + b


def _sub(a: Rate, b: Rate) -> Rate:
    return None if a is None or b is None else a - b


def _sum(values: Iterable[Rate]) -> Rate:
    total = ZERO
    for v in values:
        if v is None:
            return None
        total += v
    return total


def _float(value: Rate) -> float | None:
    return None if value is None else float(value)
