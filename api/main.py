import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.deps import get_session_factory
from api.router import api_router
from api.routes.integrations.sync import SyncConflictError
from integrations.sync import fail_interrupted_jobs

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    with get_session_factory().begin() as session:
        if count := fail_interrupted_jobs(session):
            log.warning("marked %d interrupted sync job(s) as failed", count)
    yield


app = FastAPI(title="unified-ledger-svc", lifespan=lifespan)
app.include_router(api_router)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


@app.exception_handler(SyncConflictError)
async def _sync_conflict(request: Request, exc: SyncConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc), "code": exc.code},
    )
