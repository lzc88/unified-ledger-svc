from fastapi import APIRouter

from api.routes import integrations, portfolio

api_router = APIRouter()
api_router.include_router(integrations.router)
api_router.include_router(portfolio.router)
