from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import CurrentUser, SessionFactory, get_ibkr_adapter
from api.routes.integrations.sync import SyncConflictError, sync_router
from api.schemas.connection import IbkrConnection, IbkrConnectionUpdate
from integrations.base import BrokerAdapter
from integrations.ibkr.connection import (
    TokenRequiredError,
    disconnect,
    get_connection,
    save_connection,
)
from integrations.sync import ActiveJobError

router = APIRouter(prefix="/ibkr", tags=["ibkr"])
router.include_router(sync_router(get_ibkr_adapter))

Broker = Annotated[BrokerAdapter, Depends(get_ibkr_adapter)]


@router.get("/connection")
def get_ibkr_connection(
    user: CurrentUser, session_factory: SessionFactory, broker: Broker
) -> IbkrConnection:
    with session_factory() as session:
        connection = get_connection(session, broker.broker_id, user.user_id)

    return IbkrConnection.model_validate(connection)


@router.put("/connection")
def put_ibkr_connection(
    body: IbkrConnectionUpdate,
    user: CurrentUser,
    session_factory: SessionFactory,
    broker: Broker,
) -> IbkrConnection:
    try:
        with session_factory.begin() as session:
            connection = save_connection(
                session,
                broker.broker_id,
                user.user_id,
                query_id=body.query_id,
                token=body.token,
                openfigi_key=body.openfigi_key,
                update_openfigi="openfigi_key" in body.model_fields_set,
            )
    except TokenRequiredError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return IbkrConnection.model_validate(connection)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
def delete_ibkr_connection(
    user: CurrentUser,
    session_factory: SessionFactory,
    broker: Broker,
    purge_history: bool = False,
) -> Response:
    try:
        with session_factory.begin() as session:
            disconnect(session, broker.broker_id, user.user_id, purge=purge_history)
    except ActiveJobError as exc:
        raise SyncConflictError("job_active", str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
