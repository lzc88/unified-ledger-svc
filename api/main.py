import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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


app = FastAPI(title="unified-ledger-svc", lifespan=lifespan)
app.include_router(api_router)
