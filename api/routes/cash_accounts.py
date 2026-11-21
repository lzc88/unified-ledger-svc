import uuid

from fastapi import APIRouter, HTTPException, Response, status

from api.deps import CurrentUser, SessionFactory
from api.schemas.cash_accounts import CashAccountCreate, CashAccountUpdate
from cash.service import (
    CashAccountNotFoundError,
    CashAccountView,
    DuplicateCashAccountError,
    create_account,
    delete_account,
    list_accounts,
    update_account,
)

router = APIRouter(prefix="/cash-accounts", tags=["cash-accounts"])


@router.get("")
def get_cash_accounts(
    user: CurrentUser, session_factory: SessionFactory
) -> list[CashAccountView]:
    with session_factory() as session:
        rows = list_accounts(session, user.user_id)

    return [CashAccountView.from_row(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def post_cash_account(
    body: CashAccountCreate, user: CurrentUser, session_factory: SessionFactory
) -> CashAccountView:
    try:
        with session_factory.begin() as session:
            row = create_account(session, user.user_id, **body.model_dump())
    except DuplicateCashAccountError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return CashAccountView.from_row(row)


@router.patch("/{account_id}")
def patch_cash_account(
    account_id: uuid.UUID,
    body: CashAccountUpdate,
    user: CurrentUser,
    session_factory: SessionFactory,
) -> CashAccountView:
    try:
        with session_factory.begin() as session:
            row = update_account(session, user.user_id, account_id, body.changes())
    except CashAccountNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DuplicateCashAccountError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return CashAccountView.from_row(row)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_cash_account(
    account_id: uuid.UUID, user: CurrentUser, session_factory: SessionFactory
) -> Response:
    try:
        with session_factory.begin() as session:
            delete_account(session, user.user_id, account_id)
    except CashAccountNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
