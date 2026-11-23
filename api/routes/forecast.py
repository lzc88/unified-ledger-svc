from fastapi import APIRouter, HTTPException, status
from fastapi.exceptions import RequestValidationError

from api.deps import CurrentUser, SessionFactory
from api.schemas.forecast import ForecastPlanIn, ForecastPlanView
from forecast.service import (
    ForecastPlanNotFoundError,
    UnknownCashAccountError,
    get_plan,
    replace_plan,
)

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("/plan")
def read_plan(user: CurrentUser, session_factory: SessionFactory) -> ForecastPlanView:
    try:
        with session_factory() as session:
            return get_plan(session, user.user_id)
    except ForecastPlanNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.put("/plan")
def put_plan(
    body: ForecastPlanIn, user: CurrentUser, session_factory: SessionFactory
) -> ForecastPlanView:
    try:
        with session_factory.begin() as session:
            return replace_plan(session, user.user_id, body)
    except UnknownCashAccountError as exc:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "destinations", index, "cash_account_id"),
                    "msg": "cash account not found.",
                }
                for index in exc.indices
            ]
        ) from exc
