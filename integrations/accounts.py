from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Account


class AccountNotFoundError(Exception):
    pass


class LastIncludedAccountError(Exception):
    pass


def list_accounts(session: Session, broker_id: str, user_id: str) -> Sequence[Account]:
    return session.scalars(
        select(Account)
        .where(Account.from_broker_id == broker_id, Account.from_user_id == user_id)
        .order_by(Account.account_id)
    ).all()


def set_included(
    session: Session, broker_id: str, user_id: str, account_id: str, included: bool
) -> Account:
    accounts = session.scalars(
        select(Account)
        .where(Account.from_broker_id == broker_id, Account.from_user_id == user_id)
        .order_by(Account.account_id)
        .with_for_update()
    ).all()

    account = next((row for row in accounts if row.account_id == account_id), None)
    if account is None:
        raise AccountNotFoundError(f"{broker_id} account {account_id!r} not found")

    if account.included == included:
        return account

    others = [row for row in accounts if row is not account and row.included]
    if not included and not others:
        raise LastIncludedAccountError(
            f"at least one {broker_id} account must stay included"
        )

    account.included = included
    session.flush()
    return account
