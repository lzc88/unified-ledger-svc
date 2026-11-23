from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, Market, SessionFactory
from api.schemas.portfolio import Currency
from config.config import PORTFOLIO_DEFAULT_CURRENCY, SNAPSHOT_TIMEZONE
from portfolio.snapshots import load_snapshots
from portfolio.summary import NoSnapshotsError, PortfolioSummary, build_summary

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("")
def get_portfolio(
    user: CurrentUser,
    session_factory: SessionFactory,
    market: Market,
    currency: Currency = PORTFOLIO_DEFAULT_CURRENCY,
) -> PortfolioSummary:
    with session_factory() as session:
        snapshots = load_snapshots(session, user.user_id)

    today = datetime.now(SNAPSHOT_TIMEZONE).date()
    try:
        return build_summary(user.user_id, snapshots, market, currency, today)
    except NoSnapshotsError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
