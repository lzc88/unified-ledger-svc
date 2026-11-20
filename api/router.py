from fastapi import APIRouter

from api.routes import auth, integrations, ledger, portfolio

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(integrations.router)
api_router.include_router(ledger.router)
api_router.include_router(portfolio.router)
