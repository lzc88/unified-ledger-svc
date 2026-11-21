from datetime import date

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, Market, SessionFactory
from api.schemas.portfolio import Currency
from cash.service import list_accounts
from config.config import PORTFOLIO_DEFAULT_CURRENCY
from portfolio.events import ledger_events
from portfolio.ledger import LedgerError
from portfolio.networth import NetWorth, build_net_worth

router = APIRouter(prefix="/net-worth", tags=["net-worth"])


@router.get("")
def get_net_worth(
    user: CurrentUser,
    session_factory: SessionFactory,
    market: Market,
    currency: Currency = PORTFOLIO_DEFAULT_CURRENCY,
) -> NetWorth:
    with session_factory() as session:
        events = ledger_events(session, user.user_id)
        accounts = list_accounts(session, user.user_id)

    try:
        return build_net_worth(
            user.user_id, events, accounts, market, currency, date.today()
        )
    except LedgerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
