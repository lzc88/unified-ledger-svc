import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas.forecast import (
    ForecastDestination,
    ForecastPlanIn,
    ForecastPlanView,
    month_start,
)
from database.models import CashAccount, ForecastPlan


class ForecastPlanNotFoundError(Exception):
    pass


class UnknownCashAccountError(Exception):
    def __init__(self, indices: list[int]) -> None:
        super().__init__(f"cash account not found for destinations {indices}")
        self.indices = indices


def get_plan(session: Session, user_id: str) -> ForecastPlanView:
    row = session.get(ForecastPlan, user_id)
    if row is None:
        raise ForecastPlanNotFoundError("forecast plan not found")

    return _view(row)


def replace_plan(session: Session, user_id: str, plan: ForecastPlanIn) -> ForecastPlanView:
    _require_owned_accounts(session, user_id, plan.destinations)

    row = session.get(ForecastPlan, user_id)
    if row is None:
        row = ForecastPlan(from_user_id=user_id)
        session.add(row)

    row.gross_income = Decimal(str(plan.gross_income))
    row.end_month = month_start(plan.end_month)
    row.remainder_destination_id = plan.remainder_destination_id
    row.destinations = [d.model_dump(mode="json") for d in plan.destinations]
    row.updated_at = func.now()

    session.flush()
    session.refresh(row)

    return _view(row)


def _require_owned_accounts(
    session: Session, user_id: str, destinations: Sequence[ForecastDestination]
) -> None:
    linked = {
        index: d.cash_account_id
        for index, d in enumerate(destinations)
        if d.cash_account_id is not None
    }
    if not linked:
        return

    owned: set[uuid.UUID] = set(
        session.scalars(
            select(CashAccount.cash_account_id).where(
                CashAccount.from_user_id == user_id,
                CashAccount.cash_account_id.in_(linked.values()),
            )
        )
    )

    missing = [index for index, account_id in linked.items() if account_id not in owned]
    if missing:
        raise UnknownCashAccountError(missing)


def _view(row: ForecastPlan) -> ForecastPlanView:
    return ForecastPlanView.model_validate(
        {
            "gross_income": float(row.gross_income),
            "end_month": row.end_month.strftime("%Y-%m"),
            "remainder_destination_id": row.remainder_destination_id,
            "destinations": row.destinations,
            "updated_at": row.updated_at,
        }
    )
