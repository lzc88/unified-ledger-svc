import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api.schemas.cpf import CpfStatementUpload
from config.config import CPF_CODES, CPF_CURRENCY
from database.models import CpfStatement, CpfTransaction, User


class CpfStatementNotFoundError(Exception):
    pass


class CpfAccountsView(BaseModel):
    oa: float
    sa: float
    ma: float
    total: float

    @classmethod
    def of(cls, oa: Decimal, sa: Decimal, ma: Decimal) -> "CpfAccountsView":
        return cls(oa=float(oa), sa=float(sa), ma=float(ma), total=float(oa + sa + ma))


class CpfStatementView(BaseModel):
    id: uuid.UUID
    generated_at: datetime
    period_start: date
    period_end: date
    opening_balance: CpfAccountsView
    closing_balance: CpfAccountsView
    transaction_count: int
    uploaded_at: datetime

    @classmethod
    def from_row(cls, row: CpfStatement, transaction_count: int) -> "CpfStatementView":
        return cls(
            id=row.statement_id,
            generated_at=row.generated_at,
            period_start=row.period_start,
            period_end=row.period_end,
            opening_balance=CpfAccountsView.of(
                row.opening_oa, row.opening_sa, row.opening_ma
            ),
            closing_balance=closing_balance(row),
            transaction_count=transaction_count,
            uploaded_at=row.created_at,
        )


class CpfUploadResult(BaseModel):
    statement: CpfStatementView
    inserted: int
    replaced: int


class CpfBalancesView(BaseModel):
    as_of: date
    currency: str
    oa: float
    sa: float
    ma: float
    total: float

    @classmethod
    def from_row(cls, row: CpfStatement) -> "CpfBalancesView":
        return cls(
            as_of=row.period_end,
            currency=CPF_CURRENCY,
            **closing_balance(row).model_dump(),
        )


class CpfTransactionView(BaseModel):
    date: date
    code: str
    description: str | None
    contribution_month: date | None
    employer: str | None
    oa: float
    sa: float
    ma: float

    @classmethod
    def from_row(cls, row: CpfTransaction) -> "CpfTransactionView":
        return cls(
            date=row.tx_date,
            code=row.code,
            description=CPF_CODES.get(row.code),
            contribution_month=row.contribution_month,
            employer=row.employer,
            oa=float(row.oa_amount),
            sa=float(row.sa_amount),
            ma=float(row.ma_amount),
        )


def closing_balance(row: CpfStatement) -> CpfAccountsView:
    return CpfAccountsView.of(row.closing_oa, row.closing_sa, row.closing_ma)


def closing_total(row: CpfStatement) -> Decimal:
    return row.closing_oa + row.closing_sa + row.closing_ma


def replace_statement(
    session: Session, user_id: str, upload: CpfStatementUpload
) -> CpfUploadResult:
    session.execute(select(User.user_id).where(User.user_id == user_id).with_for_update())

    replaced = session.execute(
        delete(CpfTransaction).where(CpfTransaction.from_user_id == user_id)
    ).rowcount
    session.execute(delete(CpfStatement).where(CpfStatement.from_user_id == user_id))

    statement = CpfStatement(
        from_user_id=user_id,
        generated_at=upload.generated_at,
        period_start=upload.period_start,
        period_end=upload.period_end,
        opening_oa=upload.opening_balance.oa,
        opening_sa=upload.opening_balance.sa,
        opening_ma=upload.opening_balance.ma,
        closing_oa=upload.closing_balance.oa,
        closing_sa=upload.closing_balance.sa,
        closing_ma=upload.closing_balance.ma,
    )
    session.add(statement)
    session.flush()

    session.add_all(
        CpfTransaction(
            from_statement_id=statement.statement_id,
            from_user_id=user_id,
            line_no=line_no,
            tx_date=tx.date,
            code=tx.code,
            contribution_month=tx.contribution_month,
            employer=tx.employer,
            oa_amount=tx.oa,
            sa_amount=tx.sa,
            ma_amount=tx.ma,
        )
        for line_no, tx in enumerate(upload.transactions)
    )
    session.flush()
    session.refresh(statement)

    inserted = len(upload.transactions)

    return CpfUploadResult(
        statement=CpfStatementView.from_row(statement, inserted),
        inserted=inserted,
        replaced=replaced,
    )


def find_statement(session: Session, user_id: str) -> CpfStatement | None:
    query = select(CpfStatement).where(CpfStatement.from_user_id == user_id)
    return session.scalars(query).one_or_none()


def get_statement(session: Session, user_id: str) -> CpfStatementView:
    row = _owned(session, user_id)
    count = session.scalar(
        select(func.count()).where(CpfTransaction.from_statement_id == row.statement_id)
    )

    return CpfStatementView.from_row(row, count or 0)


def get_balances(session: Session, user_id: str) -> CpfBalancesView:
    return CpfBalancesView.from_row(_owned(session, user_id))


def delete_statement(session: Session, user_id: str) -> None:
    row = _owned(session, user_id)
    session.execute(
        delete(CpfTransaction).where(CpfTransaction.from_statement_id == row.statement_id)
    )
    session.delete(row)


def list_transactions(
    session: Session,
    user_id: str,
    start: date | None = None,
    end: date | None = None,
    code: str | None = None,
) -> list[CpfTransactionView]:
    query = select(CpfTransaction).where(CpfTransaction.from_user_id == user_id)

    if start is not None:
        query = query.where(CpfTransaction.tx_date >= start)
    if end is not None:
        query = query.where(CpfTransaction.tx_date <= end)
    if code is not None:
        query = query.where(CpfTransaction.code == code)

    query = query.order_by(CpfTransaction.tx_date, CpfTransaction.line_no)

    return [CpfTransactionView.from_row(row) for row in session.scalars(query)]


def _owned(session: Session, user_id: str) -> CpfStatement:
    row = find_statement(session, user_id)
    if row is None:
        raise CpfStatementNotFoundError("no CPF statement uploaded")

    return row
