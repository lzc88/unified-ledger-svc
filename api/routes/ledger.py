from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from api.deps import CurrentUser, SessionFactory
from config.config import LEDGER_DEFAULT_LIMIT, LEDGER_MAX_LIMIT
from portfolio.activity import InvalidCursorError, LedgerActivity, ledger_page
from portfolio.records import EntryKind

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("")
def get_ledger(
    user: CurrentUser,
    session_factory: SessionFactory,
    limit: Annotated[int, Query(ge=1, le=LEDGER_MAX_LIMIT)] = LEDGER_DEFAULT_LIMIT,
    cursor: str | None = None,
    kind: EntryKind | None = None,
    asset_id: str | None = None,
) -> LedgerActivity:
    with session_factory() as session:
        try:
            return ledger_page(
                session,
                user.user_id,
                limit=limit,
                cursor=cursor,
                kind=kind,
                asset_id=asset_id,
            )
        except InvalidCursorError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
