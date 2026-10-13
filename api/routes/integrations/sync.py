import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from api.deps import Figi, SessionFactory
from api.schemas.sync import BackfillRequest, Job, RefreshRequest
from database.models import SyncJob, SyncKind
from integrations.base import BrokerAdapter
from integrations.openfigi import OpenFigiClient
from integrations.sync import (
    ActiveJobError,
    NoActivityError,
    create_job,
    latest_jobs,
    refresh_range,
    run_job,
)


def sync_router(get_broker: Callable[[], BrokerAdapter]) -> APIRouter:
    """Backfill, refresh and job endpoints for the broker that `get_broker` provides."""
    router = APIRouter()
    Broker = Annotated[BrokerAdapter, Depends(get_broker)]

    @router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
    def backfill(
        body: BackfillRequest,
        background: BackgroundTasks,
        session_factory: SessionFactory,
        broker: Broker,
        figi: Figi,
    ) -> Job:
        return _start(
            session_factory,
            background,
            broker,
            figi,
            body.user_id,
            SyncKind.BACKFILL,
            lambda _: (body.start, body.end),
        )

    @router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
    def refresh(
        body: RefreshRequest,
        background: BackgroundTasks,
        session_factory: SessionFactory,
        broker: Broker,
        figi: Figi,
    ) -> Job:
        return _start(
            session_factory,
            background,
            broker,
            figi,
            body.user_id,
            SyncKind.REFRESH,
            lambda session: refresh_range(session, broker, body.user_id, date.today()),
        )

    @router.get("/jobs")
    def list_jobs(
        session_factory: SessionFactory,
        broker: Broker,
        user_id: str,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> list[Job]:
        with session_factory() as session:
            jobs = latest_jobs(session, broker.broker_id, user_id, limit)
            return [Job.model_validate(job) for job in jobs]

    @router.get("/jobs/{job_id}")
    def get_job(
        job_id: uuid.UUID, session_factory: SessionFactory, broker: Broker
    ) -> Job:
        with session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None or job.from_broker_id != broker.broker_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
            return Job.model_validate(job)

    return router


def _start(
    session_factory: sessionmaker[Session],
    background: BackgroundTasks,
    broker: BrokerAdapter,
    figi: OpenFigiClient,
    user_id: str,
    kind: SyncKind,
    date_range: Callable[[Session], tuple[date, date]],
) -> Job:
    try:
        with session_factory.begin() as session:
            start, end = date_range(session)
            job = create_job(session, broker, user_id, kind, start, end)
            session.flush()
            session.refresh(job)
            created = Job.model_validate(job)
    except (ActiveJobError, NoActivityError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    background.add_task(run_job, session_factory, broker, figi, created.job_id)
    return created
