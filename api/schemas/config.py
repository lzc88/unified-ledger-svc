from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from config.config import CONFIG_VALUE_MAX_LENGTH
from user_config.service import ConfigEntry as StoredEntry

ConfigValue = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=CONFIG_VALUE_MAX_LENGTH
    ),
]


class ConfigUpdate(BaseModel):
    value: ConfigValue


class ConfigEntry(BaseModel):
    key: str
    group: str
    label: str
    description: str
    secret: bool
    required: bool
    is_set: bool
    value: str | None
    updated_at: datetime | None

    @classmethod
    def from_stored(cls, entry: StoredEntry) -> "ConfigEntry":
        return cls(
            key=entry.key,
            group=entry.meta.group,
            label=entry.meta.label,
            description=entry.meta.description,
            secret=entry.meta.secret,
            required=entry.meta.required,
            is_set=entry.is_set,
            value=entry.value,
            updated_at=entry.updated_at,
        )
