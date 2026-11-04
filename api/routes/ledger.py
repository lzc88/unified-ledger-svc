from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from api.deps import SessionFactory
from config.config import LEDGER_DEFAULT_LIMIT, LEDGER_MAX_LIMIT
from database.models import User
from portfolio.activity import InvalidCursorError, LedgerActivity, ledger_page
from portfolio.records import EntryKind

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("")
def get_ledger(
    user_id: str,
    session_factory: SessionFactory,
    limit: Annotated[int, Query(ge=1, le=LEDGER_MAX_LIMIT)] = LEDGER_DEFAULT_LIMIT,
    cursor: str | None = None,
    kind: EntryKind | None = None,
    asset_id: str | None = None,
) -> LedgerActivity:
    with session_factory() as session:
        if session.get(User, user_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

        try:
            return ledger_page(
                session,
                user_id,
                limit=limit,
                cursor=cursor,
                kind=kind,
                asset_id=asset_id,
            )
        except InvalidCursorError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
