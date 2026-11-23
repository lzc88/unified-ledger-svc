from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from config.config import (
    CONFIG_MASK_CHAR,
    CONFIG_MASK_LENGTH,
    WEBULL_ACCESS_TOKEN_CREDENTIAL,
    WEBULL_APP_KEY_CREDENTIAL,
    WEBULL_APP_SECRET_CREDENTIAL,
    WEBULL_TOKEN_STATUS_CREDENTIAL,
    WEBULL_TOKEN_STATUSES,
)
from database.models import BrokerConnection
from integrations.connections import (
    CredentialsUnreadableError,
    NotConnectedError,
    delete_connection,
    get_connection,
    read_credentials,
    save_credentials,
)
from integrations.sync import ensure_idle, purge_history
from user_config.service import mask

from .adapter import WebullAdapter


class AppSecretRequiredError(Exception):
    pass


@dataclass(frozen=True)
class WebullConnection:
    broker_id: str
    connected: bool
    app_key: str | None
    token_status: str | None
    updated_at: datetime | None
    connection: BrokerConnection | None


def describe_connection(
    session: Session, broker: WebullAdapter, user_id: str
) -> WebullConnection:
    connection = get_connection(session, broker.broker_id, user_id)
    if connection is None:
        return WebullConnection(broker.broker_id, False, None, None, None, None)

    try:
        credentials = read_credentials(connection, broker)
    except CredentialsUnreadableError:
        app_key, token_status = CONFIG_MASK_CHAR * CONFIG_MASK_LENGTH, None
    else:
        app_key = mask(credentials[WEBULL_APP_KEY_CREDENTIAL])
        token_status = credentials[WEBULL_TOKEN_STATUS_CREDENTIAL]
        if token_status not in WEBULL_TOKEN_STATUSES:
            token_status = None

    return WebullConnection(
        broker_id=broker.broker_id,
        connected=True,
        app_key=app_key,
        token_status=token_status,
        updated_at=connection.updated_at,
        connection=connection,
    )


def create_connection(
    session: Session,
    broker: WebullAdapter,
    user_id: str,
    *,
    app_key: str | None,
    app_secret: str | None,
) -> WebullConnection:
    ensure_idle(session, broker.broker_id, user_id, lock=False)

    app_key, app_secret = _resolve_keys(session, broker, user_id, app_key, app_secret)

    token = broker.client(app_key, app_secret).create_token()

    ensure_idle(session, broker.broker_id, user_id)
    save_credentials(
        session,
        broker,
        user_id,
        {
            WEBULL_APP_KEY_CREDENTIAL: app_key,
            WEBULL_APP_SECRET_CREDENTIAL: app_secret,
            WEBULL_ACCESS_TOKEN_CREDENTIAL: token.token,
            WEBULL_TOKEN_STATUS_CREDENTIAL: token.status,
        },
    )

    return describe_connection(session, broker, user_id)


def verify_connection(
    session: Session, broker: WebullAdapter, user_id: str
) -> WebullConnection:
    connection = get_connection(session, broker.broker_id, user_id)
    if connection is None:
        raise NotConnectedError(
            f"{broker.broker_id} is not connected: add it under my investments"
        )

    credentials = read_credentials(connection, broker)
    access_token = credentials[WEBULL_ACCESS_TOKEN_CREDENTIAL]

    checked = broker.client(
        credentials[WEBULL_APP_KEY_CREDENTIAL],
        credentials[WEBULL_APP_SECRET_CREDENTIAL],
        access_token,
    ).check_token(access_token)

    save_credentials(
        session,
        broker,
        user_id,
        credentials
        | {
            WEBULL_ACCESS_TOKEN_CREDENTIAL: checked.token,
            WEBULL_TOKEN_STATUS_CREDENTIAL: checked.status,
        },
    )

    return describe_connection(session, broker, user_id)


def disconnect(session: Session, broker_id: str, user_id: str) -> None:
    ensure_idle(session, broker_id, user_id)
    purge_history(session, broker_id, user_id)
    delete_connection(session, broker_id, user_id)


def _resolve_keys(
    session: Session,
    broker: WebullAdapter,
    user_id: str,
    app_key: str | None,
    app_secret: str | None,
) -> tuple[str, str]:
    if app_key is not None and app_secret is not None:
        return app_key, app_secret

    if app_key is None and app_secret is not None:
        raise AppSecretRequiredError("app key is required with a new app secret")

    stored = _stored_keys(session, broker, user_id)
    if stored is None:
        raise AppSecretRequiredError("app key and secret are required")

    stored_key, stored_secret = stored
    if app_key is None:
        return stored_key, stored_secret

    if app_key != stored_key:
        raise AppSecretRequiredError("app secret is required for a new app key")

    return app_key, stored_secret


def _stored_keys(
    session: Session, broker: WebullAdapter, user_id: str
) -> tuple[str, str] | None:
    connection = get_connection(session, broker.broker_id, user_id)
    if connection is None:
        return None

    try:
        credentials = read_credentials(connection, broker)
    except CredentialsUnreadableError:
        return None

    return (
        credentials[WEBULL_APP_KEY_CREDENTIAL],
        credentials[WEBULL_APP_SECRET_CREDENTIAL],
    )
