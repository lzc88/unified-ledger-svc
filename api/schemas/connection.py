from datetime import datetime

from pydantic import BaseModel, ConfigDict

from api.schemas.config import ConfigValue


class IbkrConnectionUpdate(BaseModel):
    token: ConfigValue | None = None
    query_id: ConfigValue


class IbkrConnection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    broker_id: str
    connected: bool
    query_id: str | None
    token: str | None
    updated_at: datetime | None
