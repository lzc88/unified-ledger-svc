from pydantic import BaseModel, ConfigDict, StrictBool


class BrokerAccount(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: str
    account_name: str | None
    included: bool


class BrokerAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    included: StrictBool
