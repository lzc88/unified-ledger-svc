from datetime import datetime

from pydantic import BaseModel, ConfigDict

from api.schemas.config import ConfigValue


class IbkrConnectionUpdate(BaseModel):
    token: ConfigValue | None = None
    query_id: ConfigValue
    openfigi_key: ConfigValue | None = None


class IbkrConnection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    broker_id: str
    connected: bool
    query_id: str | None
    token: str | None
    openfigi_key: str | None
    updated_at: datetime | None
