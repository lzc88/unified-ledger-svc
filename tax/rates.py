from datetime import date

from pydantic import BaseModel


class TaxBand(BaseModel):
    up_to: float | None
    rate: float


class TaxBracket(BaseModel):
    from_ya: int
    bands: list[TaxBand]


class EarnedIncomeRelief(BaseModel):
    max_age: int | None
    amount: float


class TaxRebate(BaseModel):
    year_of_assessment: int
    rate: float
    cap: float


class TaxRates(BaseModel):
    source_url: str
    brackets: list[TaxBracket]
    earned_income_relief: list[EarnedIncomeRelief]
    relief_cap: float
    rebates: list[TaxRebate]
    last_reviewed: date


SOURCE_URL = (
    "https://www.iras.gov.sg/taxes/individual-income-tax/"
    "basics-of-individual-income-tax/tax-residency-and-tax-rates/"
    "individual-income-tax-rates"
)

BRACKET_YA2024 = TaxBracket(
    from_ya=2024,
    bands=[
        TaxBand(up_to=20000, rate=0),
        TaxBand(up_to=30000, rate=2),
        TaxBand(up_to=40000, rate=3.5),
        TaxBand(up_to=80000, rate=7),
        TaxBand(up_to=120000, rate=11.5),
        TaxBand(up_to=160000, rate=15),
        TaxBand(up_to=200000, rate=18),
        TaxBand(up_to=240000, rate=19),
        TaxBand(up_to=280000, rate=19.5),
        TaxBand(up_to=320000, rate=20),
        TaxBand(up_to=500000, rate=22),
        TaxBand(up_to=1000000, rate=23),
        TaxBand(up_to=None, rate=24),
    ],
)

EARNED_INCOME_RELIEF = [
    EarnedIncomeRelief(max_age=54, amount=1000),
    EarnedIncomeRelief(max_age=59, amount=6000),
    EarnedIncomeRelief(max_age=None, amount=8000),
]

RELIEF_CAP = 80000

REBATES = [
    TaxRebate(year_of_assessment=2024, rate=50, cap=200),
    TaxRebate(year_of_assessment=2025, rate=60, cap=200),
]

TAX_RATES = TaxRates(
    source_url=SOURCE_URL,
    brackets=[BRACKET_YA2024],
    earned_income_relief=EARNED_INCOME_RELIEF,
    relief_cap=RELIEF_CAP,
    rebates=REBATES,
    last_reviewed=date(2026, 11, 23),
)
