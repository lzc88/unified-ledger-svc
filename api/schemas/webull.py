from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from api.schemas.config import ConfigValue
from api.schemas.sync import SyncState

TokenStatus = Literal["PENDING", "NORMAL", "INVALID", "EXPIRED"]


class WebullConnectionCreate(BaseModel):
    app_key: ConfigValue | None = None
    app_secret: ConfigValue | None = None


class WebullConnection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    broker_id: str
    connected: bool
    app_key: str | None
    token_status: TokenStatus | None
    updated_at: datetime | None
    sync: SyncState
