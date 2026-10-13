from datetime import date

from fastapi import APIRouter, HTTPException, status

from api.deps import Market, SessionFactory
from api.schemas.portfolio import Currency
from database.models import User
from portfolio.events import ledger_events
from portfolio.ledger import LedgerError
from portfolio.summary import NoActivityError, PortfolioSummary, build_summary

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("")
def get_portfolio(
    user_id: str,
    session_factory: SessionFactory,
    market: Market,
    currency: Currency = "SGD",
) -> PortfolioSummary:
    with session_factory() as session:
        if session.get(User, user_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
        events = ledger_events(session, user_id)
    try:
        return build_summary(user_id, events, market, currency, date.today())
    except NoActivityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except LedgerError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
