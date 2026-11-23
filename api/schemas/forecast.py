import re
import uuid
from calendar import month_abbr
from collections import Counter
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from config.config import (
    FORECAST_DESTINATION_ID_MAX_LENGTH,
    FORECAST_DESTINATION_NAME_MAX_LENGTH,
    FORECAST_MAX_DESTINATIONS,
    FORECAST_MAX_MONTHS_AHEAD,
    FORECAST_TIMEZONE,
)

DestinationId = Annotated[
    str, StringConstraints(min_length=1, max_length=FORECAST_DESTINATION_ID_MAX_LENGTH)
]
DestinationName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=FORECAST_DESTINATION_NAME_MAX_LENGTH,
    ),
]
Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]

Kind = Literal["investment", "cash", "expense"]
Mode = Literal["amount", "percent"]
Source = Literal["manual", "portfolio", "cash_account"]

ALLOWED_SOURCES: dict[str, frozenset[str]] = {
    "investment": frozenset({"manual", "portfolio"}),
    "cash": frozenset({"manual", "cash_account"}),
    "expense": frozenset({"manual"}),
}

END_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _invalid(message: str) -> PydanticCustomError:
    return PydanticCustomError("value_error", message)


def _duplicates(values: list[str]) -> list[str]:
    return [value for value, count in Counter(values).items() if count > 1]


def month_start(value: str) -> date:
    match = END_MONTH_PATTERN.fullmatch(value)
    if match is None or not value.isascii():
        raise _invalid("end month: use the format yyyy-mm.")

    return date(int(match[1]), int(match[2]), 1)


def _month_index(month: date) -> int:
    return month.year * 12 + month.month - 1


def _month_label(month: date) -> str:
    return f"{month_abbr[month.month].lower()} {month.year}"


class ForecastDestination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: DestinationId
    name: DestinationName
    kind: Kind
    mode: Mode
    value: Money
    rate: Percent | None = None
    source: Source
    cash_account_id: uuid.UUID | None = None
    starting_balance: Money | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.mode == "percent" and self.value > 100:
            raise _invalid("value: a percent must be at most 100.")

        if self.kind == "expense" and self.rate is not None:
            raise _invalid("rate: must be null for an expense.")

        if self.source not in ALLOWED_SOURCES[self.kind]:
            raise _invalid(f"source: {self.source} is not allowed for {self.kind}.")

        linked = self.source == "cash_account"
        if linked and self.cash_account_id is None:
            raise _invalid("cash_account_id: required when source is cash_account.")

        if not linked and self.cash_account_id is not None:
            raise _invalid("cash_account_id: must be null unless source is cash_account.")

        takes_balance = self.source == "manual" and self.kind != "expense"
        if not takes_balance and self.starting_balance is not None:
            raise _invalid(
                "starting_balance: only allowed for a manual investment or cash destination."
            )

        return self


class ForecastPlanBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gross_income: Money
    end_month: str
    remainder_destination_id: DestinationId | None = None
    destinations: list[ForecastDestination] = Field(max_length=FORECAST_MAX_DESTINATIONS)

    @field_validator("end_month")
    @classmethod
    def _well_formed(cls, value: str) -> str:
        month_start(value)
        return value

    @field_validator("destinations")
    @classmethod
    def _unique(cls, destinations: list[ForecastDestination]) -> list[ForecastDestination]:
        if ids := _duplicates([d.id for d in destinations]):
            raise _invalid(f"destination ids must be unique: {', '.join(ids)}.")

        if names := _duplicates([d.name.casefold() for d in destinations]):
            raise _invalid(f"destination names must be unique: {', '.join(names)}.")

        if sum(d.source == "portfolio" for d in destinations) > 1:
            raise _invalid("only one destination can use the portfolio.")

        accounts = [str(d.cash_account_id) for d in destinations if d.cash_account_id]
        if _duplicates(accounts):
            raise _invalid("each cash account can only be linked once.")

        return destinations

    @model_validator(mode="after")
    def _remainder_exists(self) -> Self:
        remainder = self.remainder_destination_id
        if remainder is not None and remainder not in {d.id for d in self.destinations}:
            raise _invalid("remainder_destination_id: must match a destination id.")

        return self


class ForecastPlanIn(ForecastPlanBase):

    @field_validator("end_month")
    @classmethod
    def _within_window(cls, value: str) -> str:
        current = datetime.now(FORECAST_TIMEZONE).date().replace(day=1)
        ahead = _month_index(month_start(value)) - _month_index(current)

        if ahead < 1:
            raise _invalid(f"end month: pick a month after {_month_label(current)}.")

        if ahead > FORECAST_MAX_MONTHS_AHEAD:
            raise _invalid("end month: 50 years ahead at most.")

        return value


class ForecastPlanView(ForecastPlanBase):
    updated_at: datetime
