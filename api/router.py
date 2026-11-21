from fastapi import APIRouter

from api.routes import (
    auth,
    cash_accounts,
    config,
    integrations,
    ledger,
    networth,
    portfolio,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(cash_accounts.router)
api_router.include_router(config.router)
api_router.include_router(integrations.router)
api_router.include_router(ledger.router)
api_router.include_router(networth.router)
api_router.include_router(portfolio.router)
