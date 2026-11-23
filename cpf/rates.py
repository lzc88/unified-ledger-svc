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


class CpfRates(BaseModel):
    source_url: str
    contribution: list[ContributionTable]
    interest: InterestRates


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

CPF_RATES = CpfRates(
    source_url=SOURCE_URL,
    contribution=[CONTRIBUTION_2026, CONTRIBUTION_2027],
    interest=INTEREST,
)
