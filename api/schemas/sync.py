import uuid
from datetime import date, datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from database.models import SyncKind, SyncStatus

UserId = Annotated[str, Field(min_length=1, max_length=100)]


class BackfillRequest(BaseModel):
    user_id: UserId
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class RefreshRequest(BaseModel):
    user_id: UserId


class Job(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    user_id: str = Field(validation_alias="from_user_id")
    broker_id: str = Field(validation_alias="from_broker_id")
    kind: SyncKind
    status: SyncStatus
    start_date: date
    end_date: date
    inserted: dict[str, int] | None
    skipped: list[dict[str, Any]] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
