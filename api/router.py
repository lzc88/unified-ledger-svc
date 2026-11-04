from fastapi import APIRouter

from api.routes import integrations, ledger, portfolio

api_router = APIRouter()
api_router.include_router(integrations.router)
api_router.include_router(ledger.router)
api_router.include_router(portfolio.router)
