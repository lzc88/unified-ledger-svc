import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.deps import get_openfigi_factory, get_session_factory
from api.router import api_router
from api.routes.integrations.sync import SyncConflictError
from config.config import SYNC_SCHEDULER_ENABLED
from database.db import engine
from integrations.scheduler import (
    acquire_scheduler_lock,
    create_scheduler,
    release_scheduler_lock,
)
from integrations.sync import fail_interrupted_syncs

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    session_factory = get_session_factory()
    lock = acquire_scheduler_lock(engine) if SYNC_SCHEDULER_ENABLED else None
    scheduler = None

    try:
        if lock is not None:
            with session_factory.begin() as session:
                if count := fail_interrupted_syncs(session):
                    log.warning("marked %d interrupted sync(s) as failed", count)

            scheduler = create_scheduler(session_factory, get_openfigi_factory())
            scheduler.start()
        elif SYNC_SCHEDULER_ENABLED:
            log.info("another process owns the sync scheduler")

        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        if lock is not None:
            release_scheduler_lock(lock)


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
