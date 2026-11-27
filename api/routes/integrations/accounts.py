from fastapi import APIRouter, HTTPException, status

from api.deps import Adapters, CurrentUser, SessionFactory
from api.schemas.accounts import BrokerAccount, BrokerAccountUpdate
from integrations.accounts import (
    AccountNotFoundError,
    LastIncludedAccountError,
    list_accounts,
    set_included,
)
from integrations.base import BrokerAdapter


class AccountConflictError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


router = APIRouter(tags=["accounts"])


def _broker(adapters: Adapters, slug: str) -> BrokerAdapter:
    broker = adapters.get(slug)
    if broker is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown broker {slug!r}")
    return broker


@router.get("/{slug}/accounts")
def read_accounts(
    slug: str, user: CurrentUser, session_factory: SessionFactory, adapters: Adapters
) -> list[BrokerAccount]:
    broker = _broker(adapters, slug)

    with session_factory() as session:
        accounts = list_accounts(session, broker.broker_id, user.user_id)
        return [BrokerAccount.model_validate(account) for account in accounts]


@router.patch("/{slug}/accounts/{account_id}")
def update_account(
    slug: str,
    account_id: str,
    body: BrokerAccountUpdate,
    user: CurrentUser,
    session_factory: SessionFactory,
    adapters: Adapters,
) -> BrokerAccount:
    broker = _broker(adapters, slug)

    try:
        with session_factory.begin() as session:
            account = set_included(
                session, broker.broker_id, user.user_id, account_id, body.included
            )
            return BrokerAccount.model_validate(account)
    except AccountNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except LastIncludedAccountError as exc:
        raise AccountConflictError("last_account", str(exc)) from exc
