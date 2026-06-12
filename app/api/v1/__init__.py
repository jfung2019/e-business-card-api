from fastapi import APIRouter

from app.api.v1.cards import router as cards_router
from app.api.v1.user_cards import router as user_cards_router

api_v1_router = APIRouter()
api_v1_router.include_router(cards_router)
api_v1_router.include_router(user_cards_router)
