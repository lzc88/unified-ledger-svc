from fastapi import APIRouter

from api.deps import CurrentUser
from tax.rates import TAX_RATES, TaxRates

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/rates")
def read_rates(user: CurrentUser) -> TaxRates:
    return TAX_RATES
