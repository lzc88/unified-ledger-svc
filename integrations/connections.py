import json
from collections.abc import Mapping

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.models import Broker, BrokerConnection
from user_config.crypto import UndecryptableValueError, decrypt, encrypt

from .base import BrokerAdapter


class NotConnectedError(Exception):
    pass


class CredentialsUnreadableError(Exception):
    pass


def get_connection(
    session: Session, broker_id: str, user_id: str
) -> BrokerConnection | None:
    return session.get(BrokerConnection, (user_id, broker_id))


def read_credentials(
    connection: BrokerConnection, broker: BrokerAdapter
) -> dict[str, str]:
    try:
        credentials = json.loads(decrypt(connection.credentials))
    except (UndecryptableValueError, ValueError):
        raise _unreadable(broker) from None

    if not isinstance(credentials, dict) or any(
        not isinstance(credentials.get(key), str) for key in broker.credential_keys
    ):
        raise _unreadable(broker)

    return {key: credentials[key] for key in broker.credential_keys}


def load_credentials(
    session: Session, broker: BrokerAdapter, user_id: str
) -> dict[str, str]:
    connection = get_connection(session, broker.broker_id, user_id)
    if connection is None:
        raise NotConnectedError(
            f"{broker.broker_id} is not connected: add it under my investments"
        )

    return read_credentials(connection, broker)


def save_credentials(
    session: Session,
    broker: BrokerAdapter,
    user_id: str,
    credentials: Mapping[str, str],
) -> BrokerConnection:
    session.execute(
        insert(Broker)
        .values(broker_id=broker.broker_id, broker_name=broker.broker_name)
        .on_conflict_do_nothing()
    )

    payload = encrypt(
        json.dumps({key: credentials[key] for key in broker.credential_keys})
    )

    connection = get_connection(session, broker.broker_id, user_id)
    if connection is None:
        connection = BrokerConnection(
            from_user_id=user_id,
            from_broker_id=broker.broker_id,
            credentials=payload,
        )
        session.add(connection)
    else:
        connection.credentials = payload

    session.flush()
    session.refresh(connection)

    return connection


def delete_connection(session: Session, broker_id: str, user_id: str) -> None:
    session.execute(
        delete(BrokerConnection).where(
            BrokerConnection.from_user_id == user_id,
            BrokerConnection.from_broker_id == broker_id,
        )
    )


def _unreadable(broker: BrokerAdapter) -> CredentialsUnreadableError:
    return CredentialsUnreadableError(
        f"stored {broker.broker_id} credentials can't be read; "
        "edit the broker under my investments"
    )
