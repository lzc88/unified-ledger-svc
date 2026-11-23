from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from api.deps import Adapters, CurrentUser, FigiFactory, SessionFactory
from api.schemas.sync import SyncState, sync_state
from config.config import OPENFIGI_API_KEY_KEY
from integrations.connections import (
    CredentialsUnreadableError,
    NotConnectedError,
    load_credentials,
)
from integrations.sync import ActiveSyncError, run_sync, snapshot_today, start_sync
from user_config.service import ConfigUnreadableError, read_config


class SyncConflictError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


CONFLICT_CODES: dict[type[Exception], str] = {
    ActiveSyncError: "sync_active",
    NotConnectedError: "config_missing",
    CredentialsUnreadableError: "config_unreadable",
    ConfigUnreadableError: "config_unreadable",
}

router = APIRouter(tags=["sync"])


@router.post("/{slug}/sync", status_code=status.HTTP_202_ACCEPTED)
def sync(
    slug: str,
    user: CurrentUser,
    background: BackgroundTasks,
    session_factory: SessionFactory,
    adapters: Adapters,
    figi_factory: FigiFactory,
) -> SyncState:
    broker = adapters.get(slug)
    if broker is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown broker {slug!r}")

    try:
        with session_factory.begin() as session:
            load_credentials(session, broker, user.user_id)
            read_config(session, user.user_id, OPENFIGI_API_KEY_KEY)

            connection = start_sync(session, broker, user.user_id)
            state = sync_state(connection, broker.broker_id)
    except tuple(CONFLICT_CODES) as exc:
        raise SyncConflictError(CONFLICT_CODES[type(exc)], str(exc)) from exc

    background.add_task(
        run_sync, session_factory, broker, figi_factory, user.user_id, snapshot_today()
    )
    return state
