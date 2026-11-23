import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, func, or_, update
from sqlalchemy.orm import Session, sessionmaker

from config.config import (
    OPENFIGI_API_KEY_KEY,
    SYNC_INTERNAL_ERROR,
    SYNC_INTERRUPTED_ERROR,
    SYNC_STALE_AFTER,
    SYNC_STALE_ERROR,
)
from database.models import Account, BrokerConnection, SyncStatus
from user_config.service import ConfigUnreadableError, read_config

from .base import BrokerAdapter, FormatError, IntegrationError, SkippedRow, Snapshot
from .connections import (
    CredentialsUnreadableError,
    NotConnectedError,
    get_connection,
    load_credentials,
)
from .load import known_broker_assets, store_snapshot
from .openfigi import OpenFigiClient, assign_figis

log = logging.getLogger(__name__)

FigiFactory = Callable[[str | None], OpenFigiClient]


class ActiveSyncError(Exception):
    pass


@dataclass(frozen=True)
class SyncSummary:
    broker_id: str
    status: SyncStatus | None
    last_synced_at: datetime | None
    error: str | None
    skipped: list[dict[str, str | None]]


def is_stale(connection: BrokerConnection) -> bool:
    started = connection.last_sync_started_at
    return (
        connection.last_sync_status == SyncStatus.RUNNING
        and started is not None
        and datetime.now(UTC) - started > SYNC_STALE_AFTER
    )


def sync_summary(connection: BrokerConnection | None, broker_id: str) -> SyncSummary:
    if connection is None:
        return SyncSummary(broker_id, None, None, None, [])

    skipped = list(connection.last_sync_skipped or [])

    if is_stale(connection):
        return SyncSummary(
            broker_id,
            SyncStatus.FAILED,
            connection.last_synced_at,
            SYNC_STALE_ERROR,
            skipped,
        )

    return SyncSummary(
        broker_id=broker_id,
        status=connection.last_sync_status,
        last_synced_at=connection.last_synced_at,
        error=connection.last_sync_error,
        skipped=skipped,
    )


def snapshot_date_for(broker: BrokerAdapter, snapshot: Snapshot) -> date:
    if snapshot.as_of is not None:
        return snapshot.as_of

    return datetime.now(broker.timezone).date()


def start_sync(
    session: Session, broker: BrokerAdapter, user_id: str
) -> BrokerConnection:
    connection = session.scalars(
        update(BrokerConnection)
        .where(
            BrokerConnection.from_user_id == user_id,
            BrokerConnection.from_broker_id == broker.broker_id,
            or_(
                BrokerConnection.last_sync_status.is_(None),
                BrokerConnection.last_sync_status != SyncStatus.RUNNING,
                BrokerConnection.last_sync_started_at.is_(None),
                BrokerConnection.last_sync_started_at < func.now() - SYNC_STALE_AFTER,
            ),
        )
        .values(
            last_sync_status=SyncStatus.RUNNING,
            last_sync_error=None,
            last_sync_started_at=func.now(),
            updated_at=BrokerConnection.updated_at,
        )
        .returning(BrokerConnection)
        .execution_options(populate_existing=True)
    ).one_or_none()

    if connection is not None:
        return connection

    if get_connection(session, broker.broker_id, user_id) is None:
        raise NotConnectedError(
            f"{broker.broker_id} is not connected: add it under my investments"
        )
    raise ActiveSyncError(f"an {broker.broker_id} sync is already in progress")


def run_sync(
    session_factory: sessionmaker[Session],
    broker: BrokerAdapter,
    figi_factory: FigiFactory,
    user_id: str,
    snapshot_date: date | None = None,
) -> None:
    try:
        with session_factory() as session:
            credentials = load_credentials(session, broker, user_id)
            openfigi_key = read_config(session, user_id, OPENFIGI_API_KEY_KEY)

        snapshot = broker.fetch_snapshot(credentials)

        with session_factory() as session:
            known = known_broker_assets(session, broker.broker_id, snapshot.assets)
        assign_figis(snapshot, known, figi_factory(openfigi_key))

        day = snapshot_date or snapshot_date_for(broker, snapshot)
        skipped = [_skipped(row) for row in snapshot.skipped]

        with session_factory.begin() as session:
            stored = store_snapshot(session, broker, snapshot, user_id, day)
            _finish(
                session,
                broker.broker_id,
                user_id,
                SyncStatus.SUCCEEDED,
                None,
                skipped,
            )

        log.info(
            "%s sync for %s stored %s for %s, skipped %d row(s)",
            broker.broker_id,
            user_id,
            stored,
            day.isoformat(),
            len(skipped),
        )
        return
    except (
        NotConnectedError,
        CredentialsUnreadableError,
        ConfigUnreadableError,
        IntegrationError,
        FormatError,
    ) as exc:
        error = str(exc)
    except Exception:
        log.exception("%s sync for %s failed", broker.broker_id, user_id)
        error = SYNC_INTERNAL_ERROR

    try:
        with session_factory.begin() as session:
            _finish(session, broker.broker_id, user_id, SyncStatus.FAILED, error)
    except Exception:
        log.exception(
            "could not record the failed %s sync for %s", broker.broker_id, user_id
        )


def fail_interrupted_syncs(session: Session) -> int:
    result = session.execute(
        update(BrokerConnection)
        .where(
            BrokerConnection.last_sync_status == SyncStatus.RUNNING,
            or_(
                BrokerConnection.last_sync_started_at.is_(None),
                BrokerConnection.last_sync_started_at < func.now() - SYNC_STALE_AFTER,
            ),
        )
        .values(
            last_sync_status=SyncStatus.FAILED,
            last_sync_error=SYNC_INTERRUPTED_ERROR,
            updated_at=BrokerConnection.updated_at,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def ensure_idle(
    session: Session, broker_id: str, user_id: str, *, lock: bool = True
) -> None:
    connection = session.get(
        BrokerConnection, (user_id, broker_id), with_for_update=lock or None
    )
    if (
        connection is not None
        and connection.last_sync_status == SyncStatus.RUNNING
        and not is_stale(connection)
    ):
        raise ActiveSyncError("a sync is running")


def purge_history(session: Session, broker_id: str, user_id: str) -> None:
    session.execute(
        delete(Account)
        .where(Account.from_broker_id == broker_id, Account.from_user_id == user_id)
        .execution_options(synchronize_session=False)
    )


def _finish(
    session: Session,
    broker_id: str,
    user_id: str,
    status: SyncStatus,
    error: str | None,
    skipped: list[dict[str, str | None]] | None = None,
) -> None:
    values: dict[str, Any] = {
        "last_sync_status": status,
        "last_sync_error": error,
        "updated_at": BrokerConnection.updated_at,
    }
    if status is SyncStatus.SUCCEEDED:
        values["last_synced_at"] = func.now()
        values["last_sync_skipped"] = skipped or []

    session.execute(
        update(BrokerConnection)
        .where(
            BrokerConnection.from_user_id == user_id,
            BrokerConnection.from_broker_id == broker_id,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )


def _skipped(row: SkippedRow) -> dict[str, str | None]:
    return {
        "section": row.section,
        "id": row.transaction_id,
        "symbol": row.attributes.get("symbol"),
        "reason": row.reason,
    }
