import logging
from collections.abc import Mapping
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from config.config import (
    SYNC_DAILY_HOUR,
    SYNC_DAILY_MINUTE,
    SYNC_MISFIRE_GRACE_SECONDS,
    SYNC_SCHEDULER_LOCK_ID,
    SYNC_TIMEZONE,
)
from database.models import BrokerConnection

from .base import BrokerAdapter
from .connections import NotConnectedError
from .registry import ADAPTERS
from .sync import ActiveSyncError, FigiFactory, run_sync, snapshot_today, start_sync

log = logging.getLogger(__name__)

DAILY_SYNC_JOB_ID = "daily-sync"


def sync_all(
    session_factory: sessionmaker[Session],
    figi_factory: FigiFactory,
    adapters: Mapping[str, BrokerAdapter] = ADAPTERS,
    today: date | None = None,
) -> int:
    brokers = {adapter.broker_id: adapter for adapter in adapters.values()}

    with session_factory() as session:
        targets = session.execute(
            select(BrokerConnection.from_user_id, BrokerConnection.from_broker_id)
        ).all()

    started = 0
    for user_id, broker_id in targets:
        broker = brokers.get(broker_id)
        if broker is None:
            log.warning("no adapter for %s; skipping %s", broker_id, user_id)
            continue

        day = today or snapshot_today()
        if _sync_one(session_factory, broker, figi_factory, user_id, day):
            started += 1

    return started


def acquire_scheduler_lock(engine: Engine) -> Connection | None:
    connection = engine.connect()
    acquired = connection.scalar(
        text("SELECT pg_try_advisory_lock(:id)"), {"id": SYNC_SCHEDULER_LOCK_ID}
    )
    connection.commit()

    if acquired:
        return connection

    connection.close()
    return None


def release_scheduler_lock(connection: Connection) -> None:
    try:
        connection.execute(
            text("SELECT pg_advisory_unlock(:id)"), {"id": SYNC_SCHEDULER_LOCK_ID}
        )
        connection.commit()
    finally:
        connection.close()


def create_scheduler(
    session_factory: sessionmaker[Session], figi_factory: FigiFactory
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=SYNC_TIMEZONE)

    scheduler.add_job(
        sync_all,
        CronTrigger(
            hour=SYNC_DAILY_HOUR, minute=SYNC_DAILY_MINUTE, timezone=SYNC_TIMEZONE
        ),
        args=[session_factory, figi_factory],
        id=DAILY_SYNC_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=SYNC_MISFIRE_GRACE_SECONDS,
    )

    return scheduler


def _sync_one(
    session_factory: sessionmaker[Session],
    broker: BrokerAdapter,
    figi_factory: FigiFactory,
    user_id: str,
    today: date,
) -> bool:
    try:
        with session_factory.begin() as session:
            start_sync(session, broker, user_id)
    except (ActiveSyncError, NotConnectedError) as exc:
        log.info("skipping scheduled %s sync for %s: %s", broker.broker_id, user_id, exc)
        return False
    except Exception:
        log.exception("could not start %s sync for %s", broker.broker_id, user_id)
        return False

    try:
        run_sync(session_factory, broker, figi_factory, user_id, today)
    except Exception:
        log.exception("scheduled %s sync for %s failed", broker.broker_id, user_id)

    return True
