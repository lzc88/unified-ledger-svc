from datetime import datetime

from fastapi import APIRouter

from api.deps import CurrentUser, Market, SessionFactory
from api.schemas.portfolio import Currency
from cash.service import list_accounts
from config.config import PORTFOLIO_DEFAULT_CURRENCY, SNAPSHOT_TIMEZONE
from cpf.service import find_statement
from portfolio.networth import NetWorth, build_net_worth
from portfolio.snapshots import load_snapshots

router = APIRouter(prefix="/net-worth", tags=["net-worth"])


@router.get("")
def get_net_worth(
    user: CurrentUser,
    session_factory: SessionFactory,
    market: Market,
    currency: Currency = PORTFOLIO_DEFAULT_CURRENCY,
    include_cpf: bool = False,
) -> NetWorth:
    with session_factory() as session:
        snapshots = load_snapshots(session, user.user_id)
        accounts = list_accounts(session, user.user_id)
        cpf = find_statement(session, user.user_id)

    return build_net_worth(
        user.user_id,
        snapshots,
        accounts,
        market,
        currency,
        datetime.now(SNAPSHOT_TIMEZONE).date(),
        cpf=cpf,
        include_cpf=include_cpf,
    )
