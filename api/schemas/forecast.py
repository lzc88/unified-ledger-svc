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
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from config.config import (
    FORECAST_DESTINATION_ID_MAX_LENGTH,
    FORECAST_DESTINATION_NAME_MAX_LENGTH,
    FORECAST_MAX_DESTINATIONS,
    FORECAST_MAX_MONTHS_AHEAD,
    FORECAST_MAX_RATES,
    FORECAST_TARGET_ID_MAX_LENGTH,
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
TargetId = Annotated[
    str, StringConstraints(min_length=1, max_length=FORECAST_TARGET_ID_MAX_LENGTH)
]
Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]

Kind = Literal["investment", "cash", "expense"]
Mode = Literal["amount", "percent"]
Source = Literal["manual", "holding", "broker_cash", "cash_account"]

ALLOWED_SOURCES: dict[str, frozenset[str]] = {
    "investment": frozenset({"manual", "holding", "broker_cash"}),
    "cash": frozenset({"manual", "cash_account"}),
    "expense": frozenset({"manual"}),
}

END_MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
RATE_KEY_PATTERN = re.compile(r"(asset|broker_cash|cash_account|destination):.{1,64}")


def _invalid(message: str) -> PydanticCustomError:
    return PydanticCustomError("value_error", message)


def _duplicates(values: list[str]) -> list[str]:
    return [value for value, count in Counter(values).items() if count > 1]


def _cash_account_id(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise _invalid("target_id: must be a uuid when source is cash_account.") from None


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
    source: Source
    target_id: TargetId | None = None
    starting_balance: Money | None = None

    @property
    def is_manual_asset(self) -> bool:
        return self.source == "manual" and self.kind != "expense"

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.mode == "percent" and self.value > 100:
            raise _invalid("value: a percent must be at most 100.")

        if self.source not in ALLOWED_SOURCES[self.kind]:
            raise _invalid(f"source: {self.source} is not allowed for {self.kind}.")

        manual = self.source == "manual"
        if not manual and self.target_id is None:
            raise _invalid(f"target_id: required when source is {self.source}.")

        if manual and self.target_id is not None:
            raise _invalid("target_id: must be null when source is manual.")

        if self.source == "cash_account":
            self.target_id = str(_cash_account_id(self.target_id))

        if not self.is_manual_asset and self.starting_balance is not None:
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
    rates: dict[str, Percent] = Field(default_factory=dict)

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

        return destinations

    @field_validator("rates")
    @classmethod
    def _rates_well_formed(cls, rates: dict[str, float]) -> dict[str, float]:
        if len(rates) > FORECAST_MAX_RATES:
            raise _invalid(f"rates: {FORECAST_MAX_RATES} entries at most.")

        if malformed := [key for key in rates if not RATE_KEY_PATTERN.fullmatch(key)]:
            raise _invalid(f"rates: unknown keys: {', '.join(malformed)}.")

        return rates

    @field_validator("rates")
    @classmethod
    def _rates_match_destinations(
        cls, rates: dict[str, float], info: ValidationInfo
    ) -> dict[str, float]:
        destinations: list[ForecastDestination] | None = info.data.get("destinations")
        if destinations is None:
            return rates

        manual = {f"destination:{d.id}" for d in destinations if d.is_manual_asset}
        unmatched = [
            key for key in rates if key.startswith("destination:") and key not in manual
        ]
        if unmatched:
            raise _invalid(
                "rates: must name a manual investment or cash destination: "
                f"{', '.join(unmatched)}."
            )

        return rates

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
