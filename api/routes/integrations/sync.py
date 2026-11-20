import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from api.deps import CurrentUser, FigiFactory, SessionFactory
from api.schemas.sync import BackfillRequest, Job
from config.config import API_JOBS_DEFAULT_LIMIT, API_JOBS_MAX_LIMIT
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
from user_config.service import (
    ConfigMissingError,
    ConfigUnreadableError,
    require,
    resolve,
)


def sync_router(get_broker: Callable[[], BrokerAdapter]) -> APIRouter:
    """Backfill, refresh and job endpoints for the broker that `get_broker` provides."""
    router = APIRouter()
    Broker = Annotated[BrokerAdapter, Depends(get_broker)]

    @router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
    def backfill(
        body: BackfillRequest,
        user: CurrentUser,
        background: BackgroundTasks,
        session_factory: SessionFactory,
        broker: Broker,
        figi_factory: FigiFactory,
    ) -> Job:
        return _start(
            session_factory,
            background,
            broker,
            figi_factory,
            user.user_id,
            SyncKind.BACKFILL,
            lambda _: (body.start, body.end),
        )

    @router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
    def refresh(
        user: CurrentUser,
        background: BackgroundTasks,
        session_factory: SessionFactory,
        broker: Broker,
        figi_factory: FigiFactory,
    ) -> Job:
        return _start(
            session_factory,
            background,
            broker,
            figi_factory,
            user.user_id,
            SyncKind.REFRESH,
            lambda session: refresh_range(session, broker, user.user_id, date.today()),
        )

    @router.get("/jobs")
    def list_jobs(
        user: CurrentUser,
        session_factory: SessionFactory,
        broker: Broker,
        limit: Annotated[
            int, Query(ge=1, le=API_JOBS_MAX_LIMIT)
        ] = API_JOBS_DEFAULT_LIMIT,
    ) -> list[Job]:
        with session_factory() as session:
            jobs = latest_jobs(session, broker.broker_id, user.user_id, limit)
            return [Job.model_validate(job) for job in jobs]

    @router.get("/jobs/{job_id}")
    def get_job(
        job_id: uuid.UUID, user: CurrentUser, session_factory: SessionFactory, broker: Broker
    ) -> Job:
        with session_factory() as session:
            job = session.get(SyncJob, job_id)
            if (
                job is None
                or job.from_broker_id != broker.broker_id
                or job.from_user_id != user.user_id
            ):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
            return Job.model_validate(job)

    return router


def _start(
    session_factory: sessionmaker[Session],
    background: BackgroundTasks,
    broker: BrokerAdapter,
    figi_factory: Callable[[str | None], OpenFigiClient],
    user_id: str,
    kind: SyncKind,
    date_range: Callable[[Session], tuple[date, date]],
) -> Job:
    try:
        with session_factory.begin() as session:
            require(resolve(session, user_id), broker.config_keys, broker.broker_id)

            start, end = date_range(session)
            job = create_job(session, broker, user_id, kind, start, end)
            session.flush()
            session.refresh(job)
            created = Job.model_validate(job)
    except (
        ActiveJobError,
        NoActivityError,
        ConfigMissingError,
        ConfigUnreadableError,
    ) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    background.add_task(run_job, session_factory, broker, figi_factory, created.job_id)
    return created
