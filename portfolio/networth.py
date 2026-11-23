from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel

from cash.service import CashAccountView
from config.config import CPF_CURRENCY
from cpf.service import closing_total
from database.models import CashAccount, CpfStatement

from .market import MarketData, fx_symbol
from .snapshots import AccountSnapshot
from .summary import NoSnapshotsError, Rate, _add, _float, _mul, _sum, build_summary


class Investments(BaseModel):
    value: float | None
    cash: float | None
    market_value: float | None


class ValuedCashAccount(CashAccountView):
    value: float | None


class Cash(BaseModel):
    value: float | None
    accounts: list[ValuedCashAccount]


class Cpf(BaseModel):
    value: float | None
    as_of: date
    oa: float | None
    sa: float | None
    ma: float | None


class NetWorth(BaseModel):
    currency: str
    as_of: datetime
    net_worth: float | None
    includes_cpf: bool
    investments: Investments
    cash: Cash
    cpf: Cpf | None
    fx_rates: dict[str, float]
    warnings: list[str]


def build_net_worth(
    user_id: str,
    snapshots: Sequence[AccountSnapshot],
    accounts: Sequence[CashAccount],
    market: MarketData,
    currency: str,
    today: date,
    cpf: CpfStatement | None = None,
    include_cpf: bool = False,
) -> NetWorth:
    investments, fx_rates, warnings = _investments(
        user_id, snapshots, market, currency, today
    )

    fx = _fx(accounts, cpf, market, currency, warnings)
    fx_rates |= {c: float(r) for c, r in fx.items() if r is not None}

    cash_value = _sum(_mul(row.balance, fx[row.currency]) for row in accounts)

    invested = investments.value
    invested_value = None if invested is None else Decimal(str(invested))

    total = _add(invested_value, cash_value)
    includes_cpf = include_cpf and cpf is not None
    if includes_cpf:
        total = _add(total, _mul(closing_total(cpf), fx[CPF_CURRENCY]))

    return NetWorth(
        currency=currency,
        as_of=datetime.now(UTC),
        net_worth=_float(total),
        includes_cpf=includes_cpf,
        investments=investments,
        cash=Cash(
            value=_float(cash_value),
            accounts=[_valued(row, fx) for row in accounts],
        ),
        cpf=None if cpf is None else _cpf(cpf, fx[CPF_CURRENCY]),
        fx_rates=fx_rates,
        warnings=warnings,
    )


def _investments(
    user_id: str,
    snapshots: Sequence[AccountSnapshot],
    market: MarketData,
    currency: str,
    today: date,
) -> tuple[Investments, dict[str, float], list[str]]:
    try:
        summary = build_summary(user_id, snapshots, market, currency, today)
    except NoSnapshotsError:
        empty = Investments(value=0, cash=0, market_value=0)
        return empty, {currency: 1.0}, []

    totals = summary.totals
    investments = Investments(
        value=totals.value, cash=totals.cash, market_value=totals.market_value
    )
    return investments, dict(summary.fx_rates), list(summary.warnings)


def _fx(
    accounts: Sequence[CashAccount],
    cpf: CpfStatement | None,
    market: MarketData,
    currency: str,
    warnings: list[str],
) -> dict[str, Rate]:
    cash_currencies = {row.currency for row in accounts}
    cpf_currencies = set() if cpf is None else {CPF_CURRENCY}

    foreign = (cash_currencies | cpf_currencies) - {currency}
    symbols = {c: fx_symbol(c, currency) for c in foreign}
    quotes = market.quotes(set(symbols.values())) if symbols else {}

    fx: dict[str, Rate] = {currency: Decimal(1)}
    for c, s in sorted(symbols.items()):
        fx[c] = quotes[s].price if s in quotes else None
        if fx[c] is not None:
            continue

        if c in cash_currencies:
            warnings.append(
                f"no {c}/{currency} rate from Yahoo ({s}); "
                f"{c} cash accounts are unconverted"
            )
        if c in cpf_currencies:
            warnings.append(
                f"no {c}/{currency} rate from Yahoo ({s}); CPF balances are unconverted"
            )

    return fx


def _valued(row: CashAccount, fx: dict[str, Rate]) -> ValuedCashAccount:
    view = CashAccountView.from_row(row)
    value = _mul(row.balance, fx[row.currency])
    return ValuedCashAccount(**view.model_dump(), value=_float(value))


def _cpf(row: CpfStatement, rate: Rate) -> Cpf:
    return Cpf(
        value=_float(_mul(closing_total(row), rate)),
        as_of=row.period_end,
        oa=_float(_mul(row.closing_oa, rate)),
        sa=_float(_mul(row.closing_sa, rate)),
        ma=_float(_mul(row.closing_ma, rate)),
    )
