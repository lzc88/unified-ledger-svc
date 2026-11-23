from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from config.config import (
    IBKR_CONFIG_KEYS,
    IBKR_CONNECTION_KEYS,
    IBKR_FLEX_QUERY_ID_KEY,
    IBKR_FLEX_TOKEN_KEY,
    OPENFIGI_API_KEY_KEY,
)
from integrations.sync import ActiveJobError, has_active_job, purge_history
from user_config.service import (
    delete_integration_values,
    display,
    integration_rows,
    set_integration_value,
)


class TokenRequiredError(Exception):
    pass


@dataclass(frozen=True)
class IbkrConnection:
    broker_id: str
    connected: bool
    query_id: str | None
    token: str | None
    openfigi_key: str | None
    updated_at: datetime | None


def get_connection(session: Session, broker_id: str, user_id: str) -> IbkrConnection:
    rows = integration_rows(session, user_id)

    def shown(key: str, secret: bool) -> str | None:
        row = rows.get(key)
        return None if row is None else display(row.encrypted_value, secret)

    present = [rows[key] for key in IBKR_CONNECTION_KEYS if key in rows]

    return IbkrConnection(
        broker_id=broker_id,
        connected=all(key in rows for key in IBKR_CONFIG_KEYS),
        query_id=shown(IBKR_FLEX_QUERY_ID_KEY, secret=False),
        token=shown(IBKR_FLEX_TOKEN_KEY, secret=True),
        openfigi_key=shown(OPENFIGI_API_KEY_KEY, secret=True),
        updated_at=max((row.updated_at for row in present), default=None),
    )


def save_connection(
    session: Session,
    broker_id: str,
    user_id: str,
    *,
    query_id: str,
    token: str | None,
    openfigi_key: str | None,
    update_openfigi: bool,
) -> IbkrConnection:
    if token is None and IBKR_FLEX_TOKEN_KEY not in integration_rows(session, user_id):
        raise TokenRequiredError("flex token is required")

    if token is not None:
        set_integration_value(session, user_id, IBKR_FLEX_TOKEN_KEY, token)

    set_integration_value(session, user_id, IBKR_FLEX_QUERY_ID_KEY, query_id)

    if update_openfigi and openfigi_key is None:
        delete_integration_values(session, user_id, [OPENFIGI_API_KEY_KEY])
    elif update_openfigi and openfigi_key is not None:
        set_integration_value(session, user_id, OPENFIGI_API_KEY_KEY, openfigi_key)

    return get_connection(session, broker_id, user_id)


def disconnect(
    session: Session, broker_id: str, user_id: str, *, purge: bool
) -> None:
    if has_active_job(session, broker_id, user_id):
        raise ActiveJobError("a sync is running")

    delete_integration_values(session, user_id, IBKR_CONNECTION_KEYS)

    if purge:
        purge_history(session, broker_id, user_id)
