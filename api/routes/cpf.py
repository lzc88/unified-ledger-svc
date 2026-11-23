from datetime import date

from fastapi import APIRouter, HTTPException, Response, status

from api.deps import CurrentUser, SessionFactory
from api.schemas.cpf import CodeQuery, CpfStatementUpload
from cpf.rates import CPF_RATES, CpfRates
from cpf.service import (
    CpfBalancesView,
    CpfStatementNotFoundError,
    CpfStatementView,
    CpfTransactionView,
    CpfUploadResult,
    delete_statement,
    get_balances,
    get_statement,
    list_transactions,
    replace_statement,
)

router = APIRouter(prefix="/cpf", tags=["cpf"])


@router.put("/statement")
def put_statement(
    body: CpfStatementUpload, user: CurrentUser, session_factory: SessionFactory
) -> CpfUploadResult:
    with session_factory.begin() as session:
        return replace_statement(session, user.user_id, body)


@router.get("/statement")
def read_statement(user: CurrentUser, session_factory: SessionFactory) -> CpfStatementView:
    try:
        with session_factory() as session:
            return get_statement(session, user.user_id)
    except CpfStatementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.delete("/statement", status_code=status.HTTP_204_NO_CONTENT)
def remove_statement(user: CurrentUser, session_factory: SessionFactory) -> Response:
    try:
        with session_factory.begin() as session:
            delete_statement(session, user.user_id)
    except CpfStatementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/balances")
def read_balances(user: CurrentUser, session_factory: SessionFactory) -> CpfBalancesView:
    try:
        with session_factory() as session:
            return get_balances(session, user.user_id)
    except CpfStatementNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/rates")
def read_rates(user: CurrentUser) -> CpfRates:
    return CPF_RATES


@router.get("/transactions")
def read_transactions(
    user: CurrentUser,
    session_factory: SessionFactory,
    start: date | None = None,
    end: date | None = None,
    code: CodeQuery = None,
) -> list[CpfTransactionView]:
    with session_factory() as session:
        return list_transactions(session, user.user_id, start, end, code)
