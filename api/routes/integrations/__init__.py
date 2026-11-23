from fastapi import APIRouter

from api.routes.integrations import ibkr, sync, webull

router = APIRouter(prefix="/integrations")
router.include_router(ibkr.router)
router.include_router(webull.router)
router.include_router(sync.router)
