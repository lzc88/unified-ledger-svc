from fastapi import APIRouter

from api.deps import get_ibkr_adapter
from api.routes.integrations.sync import sync_router

router = APIRouter(prefix="/ibkr", tags=["ibkr"])
router.include_router(sync_router(get_ibkr_adapter))
