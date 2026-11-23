import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from config.config import SYNC_REFRESH_OVERLAP_DAYS
from database.models import (
    ACTIVE_SYNC_STATUSES,
    Account,
    Broker,
    ExecutedCash,
    ExecutedFx,
    ExecutedFxOrder,
    ExecutedTrade,
    ExecutedTradeOrder,
    FxFee,
    SyncJob,
    SyncKind,
    SyncStatus,
    TradeFee,
)
from user_config.service import (
    ConfigMissingError,
    ConfigUnreadableError,
    require,
    resolve,
)

from .base import BrokerAdapter, FormatError, IntegrationError
from .load import known_broker_assets, load
from .openfigi import OpenFigiClient, assign_figis

log = logging.getLogger(__name__)


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
    return min(latest_date - timedelta(days=SYNC_REFRESH_OVERLAP_DAYS), end), end


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
    figi_factory: Callable[[str | None], OpenFigiClient],
    job_id: uuid.UUID,
) -> None:
    with session_factory.begin() as session:
        job = session.get_one(SyncJob, job_id)
        job.status = SyncStatus.RUNNING
        job.started_at = func.now()
        user_id, start, end = job.from_user_id, job.start_date, job.end_date

    outcome: dict[str, Any] = {"status": SyncStatus.FAILED}
    try:
        with session_factory() as session:
            config = resolve(session, user_id)
        require(config, broker.config_keys, broker.broker_id)

        result = broker.map(broker.fetch(start, end, config))
        with session_factory() as session:
            known = known_broker_assets(session, broker.broker_id, result.assets)
        assign_figis(result, known, figi_factory(config.get("OPENFIGI_API_KEY")))
        with session_factory.begin() as session:
            inserted = load(session, broker, result, user_id)
        outcome = {
            "status": SyncStatus.SUCCEEDED,
            "inserted": inserted,
            "skipped": [asdict(row) for row in result.skipped],
        }
    except (
        ConfigMissingError,
        ConfigUnreadableError,
        IntegrationError,
        FormatError,
        ValueError,
    ) as exc:
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


def has_active_job(session: Session, broker_id: str, user_id: str) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    SyncJob.from_broker_id == broker_id,
                    SyncJob.from_user_id == user_id,
                    SyncJob.status.in_(ACTIVE_SYNC_STATUSES),
                )
            )
        )
    )


def purge_history(session: Session, broker_id: str, user_id: str) -> None:
    accounts = select(Account.account_id).where(
        Account.from_user_id == user_id, Account.from_broker_id == broker_id
    )

    trade_orders = select(ExecutedTradeOrder.trade_order_id).where(
        ExecutedTradeOrder.from_broker_id == broker_id,
        ExecutedTradeOrder.from_account_id.in_(accounts),
    )
    trades = select(ExecutedTrade.trade_id).where(
        ExecutedTrade.from_broker_id == broker_id,
        ExecutedTrade.from_trade_order_id.in_(trade_orders),
    )

    fx_orders = select(ExecutedFxOrder.fx_order_id).where(
        ExecutedFxOrder.from_broker_id == broker_id,
        ExecutedFxOrder.from_account_id.in_(accounts),
    )
    fx = select(ExecutedFx.fx_id).where(
        ExecutedFx.from_broker_id == broker_id,
        ExecutedFx.from_fx_order_id.in_(fx_orders),
    )

    statements = (
        delete(TradeFee).where(
            TradeFee.from_broker_id == broker_id, TradeFee.from_trade_id.in_(trades)
        ),
        delete(ExecutedTrade).where(
            ExecutedTrade.from_broker_id == broker_id,
            ExecutedTrade.from_trade_order_id.in_(trade_orders),
        ),
        delete(ExecutedTradeOrder).where(
            ExecutedTradeOrder.from_broker_id == broker_id,
            ExecutedTradeOrder.from_account_id.in_(accounts),
        ),
        delete(FxFee).where(FxFee.from_broker_id == broker_id, FxFee.from_fx_id.in_(fx)),
        delete(ExecutedFx).where(
            ExecutedFx.from_broker_id == broker_id,
            ExecutedFx.from_fx_order_id.in_(fx_orders),
        ),
        delete(ExecutedFxOrder).where(
            ExecutedFxOrder.from_broker_id == broker_id,
            ExecutedFxOrder.from_account_id.in_(accounts),
        ),
        delete(ExecutedCash).where(
            ExecutedCash.from_broker_id == broker_id,
            ExecutedCash.from_account_id.in_(accounts),
        ),
        delete(SyncJob).where(
            SyncJob.from_broker_id == broker_id, SyncJob.from_user_id == user_id
        ),
        delete(Account).where(
            Account.from_broker_id == broker_id, Account.from_user_id == user_id
        ),
    )
    for statement in statements:
        session.execute(statement.execution_options(synchronize_session=False))


def latest_jobs(
    session: Session, broker_id: str, user_id: str, limit: int
) -> list[SyncJob]:
    return list(
        session.scalars(
            select(SyncJob)
            .where(SyncJob.from_broker_id == broker_id, SyncJob.from_user_id == user_id)
            .order_by(SyncJob.created_at.desc())
            .limit(limit)
        )
    )
