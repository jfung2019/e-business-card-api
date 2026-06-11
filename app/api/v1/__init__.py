from fastapi import APIRouter

from app.api.v1.cards import router as cards_router

api_v1_router = APIRouter()
api_v1_router.include_router(cards_router)
