from fastapi import APIRouter

from app.api.v1.cards import router as cards_router
from app.api.v1.share_links import public_router as share_links_public_router
from app.api.v1.share_links import router as share_links_router
from app.api.v1.user_cards import router as user_cards_router

api_v1_router = APIRouter()
api_v1_router.include_router(cards_router)
api_v1_router.include_router(user_cards_router)
api_v1_router.include_router(share_links_router)
api_v1_router.include_router(share_links_public_router)
