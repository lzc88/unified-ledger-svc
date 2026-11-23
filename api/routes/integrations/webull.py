from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import CurrentUser, SessionFactory, get_webull_adapter
from api.routes.integrations.sync import SyncConflictError
from api.schemas.sync import sync_state
from api.schemas.webull import WebullConnection, WebullConnectionCreate
from integrations.connections import CredentialsUnreadableError, NotConnectedError
from integrations.sync import ActiveSyncError
from integrations.webull import WebullAdapter
from integrations.webull.client import WebullApiError
from integrations.webull.connection import (
    AppSecretRequiredError,
    ConnectionChangedError,
    WebullConnection as WebullConnectionState,
    create_connection,
    describe_connection,
    disconnect,
    verify_connection,
)

router = APIRouter(prefix="/webull", tags=["webull"])

Broker = Annotated[WebullAdapter, Depends(get_webull_adapter)]

CONFLICT_CODES: dict[type[Exception], str] = {
    ActiveSyncError: "sync_active",
    NotConnectedError: "config_missing",
    CredentialsUnreadableError: "config_unreadable",
    ConnectionChangedError: "connection_changed",
}


def _response(state: WebullConnectionState) -> WebullConnection:
    return WebullConnection(
        broker_id=state.broker_id,
        connected=state.connected,
        app_key=state.app_key,
        token_status=state.token_status,
        updated_at=state.updated_at,
        sync=sync_state(state.connection, state.broker_id),
    )


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, WebullApiError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    if isinstance(exc, AppSecretRequiredError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))

    return SyncConflictError(CONFLICT_CODES[type(exc)], str(exc))


def _current(
    session_factory: SessionFactory, broker: WebullAdapter, user_id: str
) -> WebullConnection:
    with session_factory() as session:
        return _response(describe_connection(session, broker, user_id))


HANDLED = (WebullApiError, AppSecretRequiredError, *CONFLICT_CODES)


@router.get("/connection")
def get_webull_connection(
    user: CurrentUser, session_factory: SessionFactory, broker: Broker
) -> WebullConnection:
    return _current(session_factory, broker, user.user_id)


@router.post("/connection")
def post_webull_connection(
    body: WebullConnectionCreate,
    user: CurrentUser,
    session_factory: SessionFactory,
    broker: Broker,
) -> WebullConnection:
    try:
        create_connection(
            session_factory,
            broker,
            user.user_id,
            app_key=body.app_key,
            app_secret=body.app_secret,
        )
    except HANDLED as exc:
        raise _translate(exc) from exc

    return _current(session_factory, broker, user.user_id)


@router.post("/connection/verify")
def verify_webull_connection(
    user: CurrentUser, session_factory: SessionFactory, broker: Broker
) -> WebullConnection:
    try:
        verify_connection(session_factory, broker, user.user_id)
    except HANDLED as exc:
        raise _translate(exc) from exc

    return _current(session_factory, broker, user.user_id)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
def delete_webull_connection(
    user: CurrentUser, session_factory: SessionFactory, broker: Broker
) -> Response:
    try:
        with session_factory.begin() as session:
            disconnect(session, broker.broker_id, user.user_id)
    except ActiveSyncError as exc:
        raise SyncConflictError("sync_active", str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
