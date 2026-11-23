from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from config.config import (
    CONFIG_MASK_CHAR,
    CONFIG_MASK_LENGTH,
    IBKR_FLEX_QUERY_ID_CREDENTIAL,
    IBKR_FLEX_TOKEN_CREDENTIAL,
)
from integrations.base import BrokerAdapter
from integrations.connections import (
    CredentialsUnreadableError,
    delete_connection,
    get_connection,
    read_credentials,
    save_credentials,
)
from integrations.sync import SyncSummary, ensure_idle, purge_history, sync_summary
from user_config.service import mask


class TokenRequiredError(Exception):
    pass


@dataclass(frozen=True)
class IbkrConnection:
    broker_id: str
    connected: bool
    query_id: str | None
    token: str | None
    updated_at: datetime | None
    sync: SyncSummary


def describe_connection(
    session: Session, broker: BrokerAdapter, user_id: str
) -> IbkrConnection:
    connection = get_connection(session, broker.broker_id, user_id)
    if connection is None:
        return IbkrConnection(
            broker_id=broker.broker_id,
            connected=False,
            query_id=None,
            token=None,
            updated_at=None,
            sync=sync_summary(None, broker.broker_id),
        )

    try:
        credentials = read_credentials(connection, broker)
    except CredentialsUnreadableError:
        query_id, token = None, CONFIG_MASK_CHAR * CONFIG_MASK_LENGTH
    else:
        query_id = credentials[IBKR_FLEX_QUERY_ID_CREDENTIAL]
        token = mask(credentials[IBKR_FLEX_TOKEN_CREDENTIAL])

    return IbkrConnection(
        broker_id=broker.broker_id,
        connected=True,
        query_id=query_id,
        token=token,
        updated_at=connection.updated_at,
        sync=sync_summary(connection, broker.broker_id),
    )


def save_connection(
    session: Session,
    broker: BrokerAdapter,
    user_id: str,
    *,
    query_id: str,
    token: str | None,
) -> IbkrConnection:
    if token is None:
        token = _stored_token(session, broker, user_id)

    save_credentials(
        session,
        broker,
        user_id,
        {IBKR_FLEX_TOKEN_CREDENTIAL: token, IBKR_FLEX_QUERY_ID_CREDENTIAL: query_id},
    )

    return describe_connection(session, broker, user_id)


def disconnect(session: Session, broker_id: str, user_id: str) -> None:
    ensure_idle(session, broker_id, user_id)

    purge_history(session, broker_id, user_id)
    delete_connection(session, broker_id, user_id)


def _stored_token(session: Session, broker: BrokerAdapter, user_id: str) -> str:
    connection = get_connection(session, broker.broker_id, user_id)
    if connection is None:
        raise TokenRequiredError("flex token is required")

    try:
        return read_credentials(connection, broker)[IBKR_FLEX_TOKEN_CREDENTIAL]
    except CredentialsUnreadableError:
        raise TokenRequiredError("flex token is required") from None
