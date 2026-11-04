from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel

from config.config import PORTFOLIO_DUST

from .ledger import ZERO, Event, Holding, Snapshot, replay
from .market import (
    MarketData,
    MarketDataError,
    Quote,
    fx_symbol,
    yahoo_symbol,
)


class NoActivityError(Exception):
    pass


class Position(BaseModel):
    asset_id: str
    symbol: str
    yahoo_symbol: str | None
    category: str
    exchange: str
    currency: str
    open: bool
    quantity: float
    avg_cost: float | None
    cost_basis: float
    price: float | None
    market_value: float | None
    unrealised: float | None
    realised: float


class Balance(BaseModel):
    currency: str
    amount: float
    value: float | None


class Totals(BaseModel):
    value: float | None
    net_capital: float | None
    cash: float | None
    market_value: float | None
    cost_basis: float | None
    unrealised: float | None
    realised: float | None


class HistoryPoint(BaseModel):
    month: str
    value: float | None
    net_capital: float | None


class PortfolioSummary(BaseModel):
    user_id: str
    currency: str
    as_of: datetime
    fx_rates: dict[str, float]
    totals: Totals
    positions: list[Position]
    cash: list[Balance]
    deposits: list[Balance]
    withdrawals: list[Balance]
    fees: list[Balance]
    history: list[HistoryPoint]
    warnings: list[str]


Rate = Decimal | None


def build_summary(
    user_id: str,
    events: Iterable[Event],
    market: MarketData,
    currency: str,
    today: date,
) -> PortfolioSummary:
    book, snapshots = replay(events)
    if not snapshots:
        raise NoActivityError(f"no ledger activity for user {user_id!r}")
    warnings: list[str] = []
    holdings = book.holdings
    symbols = _yahoo_symbols(holdings, warnings)
    capital_currencies = set(book.deposits) | set(book.withdrawals)
    foreign = (
        set(book.cash) | capital_currencies | {h.currency for h in holdings.values()}
    ) - {currency}
    fx_symbols = {c: fx_symbol(c, currency) for c in foreign}
    open_holdings = [h for h in holdings.values() if h.is_open]

    quotes = market.quotes(set(symbols.values()) | set(fx_symbols.values()))
    priceable = _priceable(holdings, symbols, quotes, warnings)
    fx: dict[str, Rate] = {currency: Decimal(1)}
    for c, s in sorted(fx_symbols.items()):
        fx[c] = quotes[s].price if s in quotes else None
        if fx[c] is None:
            warnings.append(
                f"no {c}/{currency} rate from Yahoo ({s}); {c} amounts are unconverted"
            )
    prices = {
        h.asset_id: _price(priceable.get(h.asset_id), quotes, warnings)
        for h in open_holdings
    }
    if capital_currencies - {currency}:
        warnings.append(
            f"deposits in other currencies are converted to {currency} at today's rate"
        )

    market_value = _sum(
        _mul(h.quantity, prices[h.asset_id], fx[h.currency]) for h in open_holdings
    )
    cost_basis = _sum(_mul(h.cost, fx[h.currency]) for h in open_holdings)
    cash_value = _sum(_mul(b, fx[c]) for c, b in book.cash.items())
    totals = Totals(
        value=_float(_add(cash_value, market_value)),
        net_capital=_float(
            _sum(
                _mul(book.deposits[c] - book.withdrawals[c], fx[c])
                for c in capital_currencies
            )
        ),
        cash=_float(cash_value),
        market_value=_float(market_value),
        cost_basis=_float(cost_basis),
        unrealised=_float(_sub(market_value, cost_basis)),
        realised=_float(
            _sum(_mul(h.realised, fx[h.currency]) for h in holdings.values())
        ),
    )

    positions = [
        _position(h, symbols.get(a), prices.get(a)) for a, h in holdings.items()
    ]
    positions.sort(key=lambda p: (not p.open, -(p.market_value or 0), p.symbol))
    return PortfolioSummary(
        user_id=user_id,
        currency=currency,
        as_of=datetime.now(UTC),
        fx_rates={c: float(r) for c, r in fx.items() if r is not None},
        totals=totals,
        positions=positions,
        cash=_balances(book.cash, fx),
        deposits=_balances(book.deposits, fx),
        withdrawals=_balances(book.withdrawals, fx),
        fees=_balances(book.fees, fx),
        history=_history(
            snapshots,
            holdings,
            priceable,
            currency,
            fx_symbols,
            market,
            today,
            prices,
            fx,
            warnings,
        ),
        warnings=warnings,
    )


def _yahoo_symbols(holdings: dict[str, Holding], warnings: list[str]) -> dict[str, str]:
    symbols = {}
    for asset_id, h in sorted(holdings.items()):
        symbol = yahoo_symbol(h.ticker, h.exchange)
        if symbol is None:
            warnings.append(f"no Yahoo exchange for {h.ticker} on {h.exchange}")
        else:
            symbols[asset_id] = symbol
    return symbols


def _priceable(
    holdings: dict[str, Holding],
    symbols: dict[str, str],
    quotes: dict[str, Quote],
    warnings: list[str],
) -> dict[str, str]:
    priceable = {}
    for asset_id, symbol in symbols.items():
        quote, currency = quotes.get(symbol), holdings[asset_id].currency
        if quote is not None and quote.currency != currency:
            warnings.append(
                f"{symbol} is quoted in {quote.currency} but trades in "
                f"{currency}, so it is left unpriced"
            )
        else:
            priceable[asset_id] = symbol
    return priceable


def _price(symbol: str | None, quotes: dict[str, Quote], warnings: list[str]) -> Rate:
    if symbol is None:
        return None
    quote = quotes.get(symbol)
    if quote is None:
        warnings.append(f"no live price from Yahoo for {symbol}")
        return None
    return quote.price


def _position(h: Holding, symbol: str | None, price: Rate) -> Position:
    value = _mul(h.quantity, price) if h.is_open else None
    return Position(
        asset_id=h.asset_id,
        symbol=h.ticker,
        yahoo_symbol=symbol,
        category=h.category.value,
        exchange=h.exchange,
        currency=h.currency,
        open=h.is_open,
        quantity=float(h.quantity),
        avg_cost=float(h.cost / h.quantity) if h.is_open else None,
        cost_basis=float(h.cost),
        price=_float(price),
        market_value=_float(value),
        unrealised=_float(_sub(value, h.cost)) if h.is_open else None,
        realised=float(h.realised),
    )


def _history(
    snapshots: list[Snapshot],
    holdings: dict[str, Holding],
    symbols: dict[str, str],
    currency: str,
    fx_symbols: dict[str, str],
    market: MarketData,
    today: date,
    live_prices: dict[str, Rate],
    live_fx: dict[str, Rate],
    warnings: list[str],
) -> list[HistoryPoint]:
    start, current = snapshots[0].month, today.replace(day=1)
    try:
        closes = market.monthly_closes(
            set(symbols.values()) | set(fx_symbols.values()), start
        )
    except MarketDataError as exc:
        warnings.append(f"history is unpriced: {exc}")
        closes = {}

    by_month = {s.month: s for s in snapshots}
    snapshot = snapshots[0]
    points = []
    for month in _months(start, current):
        snapshot = by_month.get(month, snapshot)
        if month == current:
            fx, prices = live_fx, live_prices
        else:
            fx = {currency: Decimal(1)}
            fx |= {c: closes.get(s, {}).get(month) for c, s in fx_symbols.items()}
            prices = {
                a: _close(closes, symbols.get(a), month) for a in snapshot.quantities
            }
        holdings_value = _sum(
            _mul(q, prices.get(a), fx.get(holdings[a].currency))
            for a, q in snapshot.quantities.items()
        )
        cash_value = _sum(_mul(b, fx.get(c)) for c, b in snapshot.cash.items())
        points.append(
            HistoryPoint(
                month=month.strftime("%Y-%m"),
                value=_float(_add(cash_value, holdings_value)),
                net_capital=_float(
                    _sum(_mul(v, fx.get(c)) for c, v in snapshot.net_capital.items())
                ),
            )
        )
    return points


def _close(
    closes: dict[str, dict[date, Decimal]], symbol: str | None, month: date
) -> Rate:
    if symbol is None:
        return None
    return closes.get(symbol, {}).get(month)


def _months(start: date, end: date) -> list[date]:
    months = []
    while start <= end:
        months.append(start)
        start = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return months


def _balances(amounts: dict[str, Decimal], fx: dict[str, Rate]) -> list[Balance]:
    return [
        Balance(currency=c, amount=float(a), value=_float(_mul(a, fx.get(c))))
        for c, a in sorted(amounts.items())
        if abs(a) >= PORTFOLIO_DUST
    ]


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
