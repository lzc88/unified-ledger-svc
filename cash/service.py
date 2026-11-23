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

UPDATABLE_FIELDS = frozenset({"label", "balance", "currency"})
DUPLICATE_CONSTRAINT = "uq_cash_accounts_from_user_id"


class CashAccountNotFoundError(Exception):
    pass


class DuplicateCashAccountError(Exception):
    pass


class CashAccountView(BaseModel):
    id: uuid.UUID
    label: str
    balance: float
    currency: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: CashAccount) -> "CashAccountView":
        return cls(
            id=row.cash_account_id,
            label=row.label,
            balance=float(row.balance),
            currency=row.currency,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def list_accounts(session: Session, user_id: str) -> list[CashAccount]:
    query = (
        select(CashAccount)
        .where(CashAccount.from_user_id == user_id)
        .order_by(CashAccount.label)
    )
    return list(session.scalars(query))


def create_account(
    session: Session,
    user_id: str,
    *,
    label: str,
    balance: Decimal,
    currency: str,
) -> CashAccount:
    row = CashAccount(
        from_user_id=user_id,
        label=label,
        balance=balance,
        currency=currency,
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
    if not changes:
        return row

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
            "a cash account with this label already exists"
        ) from None

