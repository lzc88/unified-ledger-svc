from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel

from cash.service import CashAccountView, estimated_interest
from database.models import CashAccount

from .ledger import Event
from .market import MarketData, fx_symbol
from .summary import NoActivityError, Rate, _add, _float, _mul, _sum, build_summary


class Investments(BaseModel):
    value: float | None
    cash: float | None
    market_value: float | None


class ValuedCashAccount(CashAccountView):
    value: float | None


class Cash(BaseModel):
    value: float | None
    estimated_annual_interest: float | None
    accounts: list[ValuedCashAccount]


class NetWorth(BaseModel):
    currency: str
    as_of: datetime
    net_worth: float | None
    investments: Investments
    cash: Cash
    fx_rates: dict[str, float]
    warnings: list[str]


def build_net_worth(
    user_id: str,
    events: Iterable[Event],
    accounts: Sequence[CashAccount],
    market: MarketData,
    currency: str,
    today: date,
) -> NetWorth:
    investments, fx_rates, warnings = _investments(
        user_id, events, market, currency, today
    )

    fx = _cash_fx(accounts, market, currency, warnings)
    fx_rates |= {c: float(r) for c, r in fx.items() if r is not None}

    cash_value = _sum(_mul(row.balance, fx[row.currency]) for row in accounts)
    interest = _sum(
        _mul(estimated_interest(row.balance, row.interest_rate), fx[row.currency])
        for row in accounts
        if row.interest_rate is not None
    )

    invested = investments.value
    invested_value = None if invested is None else Decimal(str(invested))

    return NetWorth(
        currency=currency,
        as_of=datetime.now(UTC),
        net_worth=_float(_add(invested_value, cash_value)),
        investments=investments,
        cash=Cash(
            value=_float(cash_value),
            estimated_annual_interest=_float(interest),
            accounts=[_valued(row, fx) for row in accounts],
        ),
        fx_rates=fx_rates,
        warnings=warnings,
    )


def _investments(
    user_id: str,
    events: Iterable[Event],
    market: MarketData,
    currency: str,
    today: date,
) -> tuple[Investments, dict[str, float], list[str]]:
    try:
        summary = build_summary(user_id, events, market, currency, today)
    except NoActivityError:
        empty = Investments(value=0, cash=0, market_value=0)
        return empty, {currency: 1.0}, []

    totals = summary.totals
    investments = Investments(
        value=totals.value, cash=totals.cash, market_value=totals.market_value
    )
    return investments, dict(summary.fx_rates), list(summary.warnings)


def _cash_fx(
    accounts: Sequence[CashAccount],
    market: MarketData,
    currency: str,
    warnings: list[str],
) -> dict[str, Rate]:
    foreign = {row.currency for row in accounts} - {currency}
    symbols = {c: fx_symbol(c, currency) for c in foreign}
    quotes = market.quotes(set(symbols.values())) if symbols else {}

    fx: dict[str, Rate] = {currency: Decimal(1)}
    for c, s in sorted(symbols.items()):
        fx[c] = quotes[s].price if s in quotes else None
        if fx[c] is None:
            warnings.append(
                f"no {c}/{currency} rate from Yahoo ({s}); "
                f"{c} cash accounts are unconverted"
            )

    return fx


def _valued(row: CashAccount, fx: dict[str, Rate]) -> ValuedCashAccount:
    view = CashAccountView.from_row(row)
    value = _mul(row.balance, fx[row.currency])
    return ValuedCashAccount(**view.model_dump(), value=_float(value))
