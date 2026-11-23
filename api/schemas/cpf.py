import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal, Self

from fastapi import Query
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from config.config import (
    CPF_ACCOUNTS,
    CPF_EMPLOYER_MAX_LENGTH,
    CPF_MAX_TRANSACTIONS,
    CPF_TIMEZONE,
)

CODE_PATTERN = "^[A-Z]{2,3}$"

Code = Annotated[str, StringConstraints(pattern=CODE_PATTERN)]
CodeQuery = Annotated[str | None, Query(pattern=CODE_PATTERN)]
Employer = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=CPF_EMPLOYER_MAX_LENGTH
    ),
]
Amount = Annotated[Decimal, Field(allow_inf_nan=False, decimal_places=2)]
Balance = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, decimal_places=2)]


class CpfBalances(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oa: Balance
    sa: Balance
    ma: Balance


class CpfTransactionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date
    code: Code
    contribution_month: dt.date | None = None
    employer: Employer | None = None
    oa: Amount
    sa: Amount
    ma: Amount

    @field_validator("contribution_month")
    @classmethod
    def _first_of_month(cls, value: dt.date | None) -> dt.date | None:
        if value is not None and value.day != 1:
            raise ValueError("contribution_month must be the first day of a month")

        return value


class CpfStatementUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: AwareDatetime
    period_start: dt.date
    period_end: dt.date
    scope: Literal["ALL"]
    opening_balance: CpfBalances
    closing_balance: CpfBalances
    transactions: list[CpfTransactionIn] = Field(max_length=CPF_MAX_TRANSACTIONS)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")

        if self.period_end > dt.datetime.now(CPF_TIMEZONE).date():
            raise ValueError("period_end must not be in the future")

        outside = [
            index
            for index, tx in enumerate(self.transactions)
            if not self.period_start <= tx.date <= self.period_end
        ]
        if outside:
            rows = ", ".join(str(i) for i in outside)
            raise ValueError(f"transactions outside the statement period: {rows}")

        unreconciled = [
            account.upper()
            for account in CPF_ACCOUNTS
            if self._expected_closing(account) != getattr(self.closing_balance, account)
        ]
        if unreconciled:
            raise ValueError(
                f"{', '.join(unreconciled)} do not reconcile: opening balance plus "
                "transactions does not equal closing balance"
            )

        return self

    def _expected_closing(self, account: str) -> Decimal:
        opening = getattr(self.opening_balance, account)
        return opening + sum(
            (getattr(tx, account) for tx in self.transactions), Decimal(0)
        )
