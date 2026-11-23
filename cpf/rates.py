from datetime import date

from pydantic import BaseModel


class ContributionBand(BaseModel):
    max_age: int | None
    employer: float
    employee: float
    phased_employee: float


class ContributionTable(BaseModel):
    effective_from: date
    ow_ceiling: float
    bands: list[ContributionBand]


class InterestRates(BaseModel):
    period_start: date
    period_end: date
    oa: float
    sa: float
    ma: float
    ra: float


class AllocationBand(BaseModel):
    max_age: int | None
    oa: float
    sa: float
    ma: float


class AllocationTable(BaseModel):
    effective_from: date
    bands: list[AllocationBand]


class ExtraInterest(BaseModel):
    rate: float
    combined_cap: float
    oa_cap: float
    senior_age: int
    senior_rate: float
    senior_cap: float


class YearAmount(BaseModel):
    year: int
    amount: float


class CpfRates(BaseModel):
    source_url: str
    contribution: list[ContributionTable]
    interest: InterestRates
    allocation: list[AllocationTable]
    extra_interest: ExtraInterest
    healthcare_sum: list[YearAmount]
    retirement_sum: list[YearAmount]
    last_reviewed: date


SOURCE_URL = (
    "https://www.cpf.gov.sg/employer/employer-obligations/"
    "how-much-cpf-contributions-to-pay"
)

OW_CEILING = 8000

CONTRIBUTION_2026 = ContributionTable(
    effective_from=date(2026, 1, 1),
    ow_ceiling=OW_CEILING,
    bands=[
        ContributionBand(max_age=55, employer=17, employee=20, phased_employee=0.6),
        ContributionBand(max_age=60, employer=16, employee=18, phased_employee=0.54),
        ContributionBand(
            max_age=65, employer=12.5, employee=12.5, phased_employee=0.375
        ),
        ContributionBand(max_age=70, employer=9, employee=7.5, phased_employee=0.225),
        ContributionBand(
            max_age=None, employer=7.5, employee=5, phased_employee=0.15
        ),
    ],
)

CONTRIBUTION_2027 = ContributionTable(
    effective_from=date(2027, 1, 1),
    ow_ceiling=OW_CEILING,
    bands=[
        ContributionBand(max_age=55, employer=17, employee=20, phased_employee=0.6),
        ContributionBand(
            max_age=60, employer=16.5, employee=19, phased_employee=0.57
        ),
        ContributionBand(max_age=65, employer=13, employee=13, phased_employee=0.39),
        ContributionBand(max_age=70, employer=9, employee=7.5, phased_employee=0.225),
        ContributionBand(
            max_age=None, employer=7.5, employee=5, phased_employee=0.15
        ),
    ],
)

INTEREST = InterestRates(
    period_start=date(2026, 10, 1),
    period_end=date(2026, 12, 31),
    oa=2.5,
    sa=4,
    ma=4,
    ra=4,
)

ALLOCATION_2026 = AllocationTable(
    effective_from=date(2026, 1, 1),
    bands=[
        AllocationBand(max_age=35, oa=0.6217, sa=0.1621, ma=0.2162),
        AllocationBand(max_age=45, oa=0.5677, sa=0.1891, ma=0.2432),
        AllocationBand(max_age=50, oa=0.5136, sa=0.2162, ma=0.2702),
        AllocationBand(max_age=55, oa=0.4055, sa=0.3108, ma=0.2837),
        AllocationBand(max_age=60, oa=0.353, sa=0.3382, ma=0.3088),
        AllocationBand(max_age=65, oa=0.14, sa=0.44, ma=0.42),
        AllocationBand(max_age=70, oa=0.0607, sa=0.303, ma=0.6363),
        AllocationBand(max_age=None, oa=0.08, sa=0.08, ma=0.84),
    ],
)

ALLOCATION_2027 = AllocationTable(
    effective_from=date(2027, 1, 1),
    bands=[
        AllocationBand(max_age=35, oa=0.6217, sa=0.1621, ma=0.2162),
        AllocationBand(max_age=45, oa=0.5677, sa=0.1891, ma=0.2432),
        AllocationBand(max_age=50, oa=0.5136, sa=0.2162, ma=0.2702),
        AllocationBand(max_age=55, oa=0.4055, sa=0.3108, ma=0.2837),
        AllocationBand(max_age=60, oa=0.3382, sa=0.3661, ma=0.2957),
        AllocationBand(max_age=65, oa=0.1347, sa=0.4615, ma=0.4038),
        AllocationBand(max_age=70, oa=0.0607, sa=0.303, ma=0.6363),
        AllocationBand(max_age=None, oa=0.08, sa=0.08, ma=0.84),
    ],
)

EXTRA_INTEREST = ExtraInterest(
    rate=1,
    combined_cap=60000,
    oa_cap=20000,
    senior_age=55,
    senior_rate=1,
    senior_cap=30000,
)

HEALTHCARE_SUM = [
    YearAmount(year=2026, amount=79000),
]

RETIREMENT_SUM = [
    YearAmount(year=2026, amount=220400),
    YearAmount(year=2027, amount=228200),
]

CPF_RATES = CpfRates(
    source_url=SOURCE_URL,
    contribution=[CONTRIBUTION_2026, CONTRIBUTION_2027],
    interest=INTEREST,
    allocation=[ALLOCATION_2026, ALLOCATION_2027],
    extra_interest=EXTRA_INTEREST,
    healthcare_sum=HEALTHCARE_SUM,
    retirement_sum=RETIREMENT_SUM,
    last_reviewed=date(2026, 11, 23),
)
