import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import CashAccount

UPDATABLE_FIELDS = frozenset(
    {"institution", "label", "balance", "currency", "interest_rate"}
)
DUPLICATE_CONSTRAINT = "uq_cash_accounts_from_user_id"


class CashAccountNotFoundError(Exception):
    pass


class DuplicateCashAccountError(Exception):
    pass


class CashAccountView(BaseModel):
    id: uuid.UUID
    institution: str
    label: str
    balance: float
    currency: str
    interest_rate: float | None
    estimated_annual_interest: float | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: CashAccount) -> "CashAccountView":
        interest = estimated_interest(row.balance, row.interest_rate)
        return cls(
            id=row.cash_account_id,
            institution=row.institution,
            label=row.label,
            balance=float(row.balance),
            currency=row.currency,
            interest_rate=_float(row.interest_rate),
            estimated_annual_interest=_float(interest),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def estimated_interest(balance: Decimal, rate: Decimal | None) -> Decimal | None:
    if rate is None:
        return None

    return balance * rate / 100


def list_accounts(session: Session, user_id: str) -> list[CashAccount]:
    query = (
        select(CashAccount)
        .where(CashAccount.from_user_id == user_id)
        .order_by(CashAccount.institution, CashAccount.label)
    )
    return list(session.scalars(query))


def create_account(
    session: Session,
    user_id: str,
    *,
    institution: str,
    label: str,
    balance: Decimal,
    currency: str,
    interest_rate: Decimal | None = None,
) -> CashAccount:
    row = CashAccount(
        from_user_id=user_id,
        institution=institution,
        label=label,
        balance=balance,
        currency=currency,
        interest_rate=interest_rate,
    )
    with _savepoint(session):
        session.add(row)

    session.refresh(row)

    return row


def update_account(
    session: Session,
    user_id: str,
    account_id: uuid.UUID,
    changes: Mapping[str, Any],
) -> CashAccount:
    unknown = set(changes) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"cannot update {', '.join(sorted(unknown))}")

    row = _owned(session, user_id, account_id)
    with _savepoint(session):
        for field, value in changes.items():
            setattr(row, field, value)

        row.updated_at = func.clock_timestamp()

    session.refresh(row)

    return row


def delete_account(session: Session, user_id: str, account_id: uuid.UUID) -> None:
    session.delete(_owned(session, user_id, account_id))


def _owned(session: Session, user_id: str, account_id: uuid.UUID) -> CashAccount:
    row = session.get(CashAccount, account_id)
    if row is None or row.from_user_id != user_id:
        raise CashAccountNotFoundError(f"cash account not found: {account_id}")

    return row


@contextmanager
def _savepoint(session: Session) -> Iterator[None]:
    try:
        with session.begin_nested():
            yield
            session.flush()
    except IntegrityError as exc:
        if DUPLICATE_CONSTRAINT not in str(exc.orig):
            raise
        raise DuplicateCashAccountError(
            "a cash account with this institution and label already exists"
        ) from None


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
