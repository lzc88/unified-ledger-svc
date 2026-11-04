from fastapi import APIRouter

from api.routes.integrations import ibkr

router = APIRouter(prefix="/integrations")
router.include_router(ibkr.router)
