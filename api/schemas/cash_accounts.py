from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from config.config import CashCurrency

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Currency = CashCurrency
Balance = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]

NON_NULLABLE = ("label", "balance", "currency")


class CashAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Text
    balance: Balance
    currency: Currency


class CashAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Text | None = None
    balance: Balance | None = None
    currency: Currency | None = None

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
