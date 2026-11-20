import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.deps import get_session_factory
from api.router import api_router
from integrations.sync import fail_interrupted_jobs

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    with get_session_factory().begin() as session:
        if count := fail_interrupted_jobs(session):
            log.warning("marked %d interrupted sync job(s) as failed", count)
    yield


SECRET_FIELDS = frozenset({"password", "value"})


app = FastAPI(title="unified-ledger-svc", lifespan=lifespan)
app.include_router(api_router)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {key: value for key, value in error.items() if key != "input"}
        if SECRET_FIELDS & set(map(str, error.get("loc", ())))
        else error
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )
