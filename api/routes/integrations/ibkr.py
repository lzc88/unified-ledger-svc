from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import CurrentUser, SessionFactory, get_ibkr_adapter
from api.routes.integrations.sync import SyncConflictError, sync_router
from api.schemas.connection import IbkrConnection, IbkrConnectionUpdate
from integrations.base import BrokerAdapter
from integrations.ibkr.connection import (
    TokenRequiredError,
    describe_connection,
    disconnect,
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
        connection = describe_connection(session, broker, user.user_id)

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
                broker,
                user.user_id,
                query_id=body.query_id,
                token=body.token,
            )
    except TokenRequiredError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return IbkrConnection.model_validate(connection)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
def delete_ibkr_connection(
    user: CurrentUser, session_factory: SessionFactory, broker: Broker
) -> Response:
    try:
        with session_factory.begin() as session:
            disconnect(session, broker.broker_id, user.user_id)
    except ActiveJobError as exc:
        raise SyncConflictError("job_active", str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
