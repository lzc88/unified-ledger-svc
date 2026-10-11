import logging
import uuid
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from database.models import (
    ACTIVE_SYNC_STATUSES,
    Account,
    Broker,
    ExecutedCash,
    ExecutedFx,
    ExecutedFxOrder,
    ExecutedTrade,
    ExecutedTradeOrder,
    SyncJob,
    SyncKind,
    SyncStatus,
    User,
)

from .base import BrokerAdapter, FormatError, IntegrationError
from .load import known_broker_assets, load
from .openfigi import OpenFigiClient, assign_figis

log = logging.getLogger(__name__)

REFRESH_OVERLAP_DAYS = 7


class ActiveJobError(Exception):
    pass


class NoActivityError(Exception):
    pass


def refresh_range(
    session: Session, broker: BrokerAdapter, user_id: str, today: date
) -> tuple[date, date]:
    broker_id = broker.broker_id
    user_accounts = select(Account.account_id).where(
        Account.from_user_id == user_id, Account.from_broker_id == broker_id
    )
    latest_cash = select(func.max(ExecutedCash.tx_datetime)).where(
        ExecutedCash.from_broker_id == broker_id,
        ExecutedCash.from_account_id.in_(user_accounts),
    )
    latest_trade = (
        select(func.max(ExecutedTrade.trade_datetime))
        .join(
            ExecutedTradeOrder,
            (ExecutedTradeOrder.trade_order_id == ExecutedTrade.from_trade_order_id)
            & (ExecutedTradeOrder.from_broker_id == ExecutedTrade.from_broker_id),
        )
        .where(
            ExecutedTradeOrder.from_broker_id == broker_id,
            ExecutedTradeOrder.from_account_id.in_(user_accounts),
        )
    )
    latest_fx = (
        select(func.max(ExecutedFx.fx_datetime))
        .join(
            ExecutedFxOrder,
            (ExecutedFxOrder.fx_order_id == ExecutedFx.from_fx_order_id)
            & (ExecutedFxOrder.from_broker_id == ExecutedFx.from_broker_id),
        )
        .where(
            ExecutedFxOrder.from_broker_id == broker_id,
            ExecutedFxOrder.from_account_id.in_(user_accounts),
        )
    )
    latest = [
        ts for ts in map(session.scalar, (latest_cash, latest_trade, latest_fx)) if ts
    ]
    if not latest:
        raise NoActivityError(
            f"no {broker_id} ledger activity for user {user_id!r}; run a backfill first"
        )
    end = today - timedelta(days=1)
    latest_date = max(latest).astimezone(broker.timezone).date()
    return min(latest_date - timedelta(days=REFRESH_OVERLAP_DAYS), end), end


def create_job(
    session: Session,
    broker: BrokerAdapter,
    user_id: str,
    kind: SyncKind,
    start: date,
    end: date,
) -> SyncJob:
    session.execute(
        insert(Broker)
        .values(broker_id=broker.broker_id, broker_name=broker.broker_name)
        .on_conflict_do_nothing()
    )
    session.execute(
        insert(User).values(user_id=user_id, user_name=user_id).on_conflict_do_nothing()
    )
    job = SyncJob(
        from_user_id=user_id,
        from_broker_id=broker.broker_id,
        kind=kind,
        status=SyncStatus.PENDING,
        start_date=start,
        end_date=end,
    )
    try:
        with session.begin_nested():
            session.add(job)
    except IntegrityError as exc:
        if (
            getattr(exc.orig.diag, "constraint_name", None)
            == "uq_sync_jobs_active_broker"
        ):
            raise ActiveJobError(
                f"an {broker.broker_id} sync job is already in progress"
            ) from exc
        raise
    return job


def run_job(
    session_factory: sessionmaker[Session],
    broker: BrokerAdapter,
    figi: OpenFigiClient,
    job_id: uuid.UUID,
) -> None:
    with session_factory.begin() as session:
        job = session.get_one(SyncJob, job_id)
        job.status = SyncStatus.RUNNING
        job.started_at = func.now()
        user_id, start, end = job.from_user_id, job.start_date, job.end_date

    outcome: dict[str, Any] = {"status": SyncStatus.FAILED}
    try:
        result = broker.map(broker.fetch(start, end))
        with session_factory() as session:
            known = known_broker_assets(session, broker.broker_id, result.assets)
        assign_figis(result, known, figi)
        with session_factory.begin() as session:
            inserted = load(session, broker, result, user_id)
        outcome = {
            "status": SyncStatus.SUCCEEDED,
            "inserted": inserted,
            "skipped": [asdict(row) for row in result.skipped],
        }
    except (IntegrationError, FormatError, ValueError) as exc:
        outcome["error"] = str(exc)
    except Exception:
        log.exception("sync job %s failed", job_id)
        outcome["error"] = "internal error; see server logs"

    with session_factory.begin() as session:
        session.execute(
            update(SyncJob)
            .where(SyncJob.job_id == job_id)
            .values(**outcome, finished_at=func.now())
        )


def fail_interrupted_jobs(session: Session) -> int:
    result = session.execute(
        update(SyncJob)
        .where(SyncJob.status.in_(ACTIVE_SYNC_STATUSES))
        .values(
            status=SyncStatus.FAILED,
            error="interrupted by server restart",
            finished_at=func.now(),
        )
    )
    return result.rowcount


def latest_jobs(session: Session, user_id: str, limit: int) -> list[SyncJob]:
    return list(
        session.scalars(
            select(SyncJob)
            .where(SyncJob.from_user_id == user_id)
            .order_by(SyncJob.created_at.desc())
            .limit(limit)
        )
    )
