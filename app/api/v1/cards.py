import logging

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth import get_current_user_id
from app.core.exceptions import CardPersistenceError, OpenRouterError, OpenRouterTimeoutError
from app.db.mongodb import get_cards_collection_dependency
from app.models.card import CapturedCardResponse
from app.models.requests import ProcessCardRequest
from app.services.card_service import CardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["cards"])


def get_card_service(
    collection: AsyncIOMotorCollection = Depends(get_cards_collection_dependency),
) -> CardService:
    return CardService(collection=collection)


@router.get(
    "",
    response_model=list[CapturedCardResponse],
    summary="List captured business cards for the authenticated user",
)
async def list_cards(
    owner_user_id: str = Depends(get_current_user_id),
    card_service: CardService = Depends(get_card_service),
) -> list[CapturedCardResponse]:
    try:
        return await card_service.list_for_user(owner_user_id)
    except CardPersistenceError as exc:
        logger.error("Database error while listing cards: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load captured cards.",
        ) from exc


@router.post(
    "/process",
    response_model=CapturedCardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Parse OCR text and persist a captured business card",
)
async def process_card(
    payload: ProcessCardRequest,
    owner_user_id: str = Depends(get_current_user_id),
    card_service: CardService = Depends(get_card_service),
) -> CapturedCardResponse:
    try:
        return await card_service.process_and_save(
            owner_user_id=owner_user_id,
            raw_ocr_text=payload.raw_ocr_text,
        )
    except OpenRouterTimeoutError as exc:
        logger.warning("OpenRouter timeout while processing card for user %s", owner_user_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM parsing service timed out. Please try again.",
        ) from exc
    except OpenRouterError as exc:
        logger.error("OpenRouter error while processing card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM parsing service is unavailable.",
        ) from exc
    except CardPersistenceError as exc:
        logger.error("Database error while saving card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save captured card.",
        ) from exc
