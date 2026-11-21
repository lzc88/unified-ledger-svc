from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Currency = Annotated[str, StringConstraints(pattern="^[A-Z]{3}$")]
Balance = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Rate = Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False)]

NON_NULLABLE = ("institution", "label", "balance", "currency")


class CashAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: Text
    label: Text
    balance: Balance
    currency: Currency
    interest_rate: Rate | None = None


class CashAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: Text | None = None
    label: Text | None = None
    balance: Balance | None = None
    currency: Currency | None = None
    interest_rate: Rate | None = None

    @model_validator(mode="after")
    def _reject_null_required_fields(self) -> Self:
        nulled = [
            field
            for field in NON_NULLABLE
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if nulled:
            raise ValueError(f"{', '.join(nulled)} cannot be null")

        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)
