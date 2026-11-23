from datetime import datetime

from pydantic import BaseModel, ConfigDict

from database.models import BrokerConnection, SyncStatus
from integrations.sync import sync_summary


class SyncState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    broker_id: str
    status: SyncStatus | None
    last_synced_at: datetime | None
    error: str | None


def sync_state(connection: BrokerConnection | None, broker_id: str) -> SyncState:
    return SyncState.model_validate(sync_summary(connection, broker_id))
