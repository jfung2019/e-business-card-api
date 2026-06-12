import logging

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth import get_current_user_id
from app.core.exceptions import CardPersistenceError, OpenRouterError, OpenRouterTimeoutError
from app.db.mongodb import get_user_cards_collection_dependency
from app.models.user_card import (
    ParsedUserCardPreview,
    ParseUserCardRequest,
    ReorderUserCardsRequest,
    UserCardCreate,
    UserCardResponse,
    UserCardUpdate,
)
from app.services.user_card_service import UserCardNotFoundError, UserCardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-cards", tags=["user-cards"])


def get_user_card_service(
    collection: AsyncIOMotorCollection = Depends(get_user_cards_collection_dependency),
) -> UserCardService:
    return UserCardService(collection=collection)


@router.get(
    "",
    response_model=list[UserCardResponse],
    summary="List the authenticated user's own business cards",
)
async def list_user_cards(
    owner_user_id: str = Depends(get_current_user_id),
    user_card_service: UserCardService = Depends(get_user_card_service),
) -> list[UserCardResponse]:
    try:
        return await user_card_service.list_for_user(owner_user_id)
    except CardPersistenceError as exc:
        logger.error("Database error while listing user cards: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load user cards.",
        ) from exc


@router.post(
    "",
    response_model=UserCardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user business card",
)
async def create_user_card(
    payload: UserCardCreate,
    owner_user_id: str = Depends(get_current_user_id),
    user_card_service: UserCardService = Depends(get_user_card_service),
) -> UserCardResponse:
    try:
        return await user_card_service.create(owner_user_id, payload)
    except CardPersistenceError as exc:
        logger.error("Database error while creating user card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user card.",
        ) from exc


@router.patch(
    "/reorder",
    response_model=list[UserCardResponse],
    summary="Reorder user business cards (first id becomes primary)",
)
async def reorder_user_cards(
    payload: ReorderUserCardsRequest,
    owner_user_id: str = Depends(get_current_user_id),
    user_card_service: UserCardService = Depends(get_user_card_service),
) -> list[UserCardResponse]:
    try:
        return await user_card_service.reorder(owner_user_id, payload.ordered_ids)
    except CardPersistenceError as exc:
        logger.error("Database error while reordering user cards: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/parse",
    response_model=ParsedUserCardPreview,
    summary="Parse OCR text into user card fields (preview only)",
)
async def parse_user_card(
    payload: ParseUserCardRequest,
    _: str = Depends(get_current_user_id),
    user_card_service: UserCardService = Depends(get_user_card_service),
) -> ParsedUserCardPreview:
    try:
        return await user_card_service.parse_preview(payload.raw_ocr_text)
    except OpenRouterTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM parsing service timed out. Please try again.",
        ) from exc
    except OpenRouterError as exc:
        logger.error("OpenRouter error while parsing user card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM parsing service is unavailable.",
        ) from exc


@router.put(
    "/{card_id}",
    response_model=UserCardResponse,
    summary="Update a user business card",
)
async def update_user_card(
    card_id: str,
    payload: UserCardUpdate,
    owner_user_id: str = Depends(get_current_user_id),
    user_card_service: UserCardService = Depends(get_user_card_service),
) -> UserCardResponse:
    try:
        return await user_card_service.update(owner_user_id, card_id, payload)
    except UserCardNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CardPersistenceError as exc:
        logger.error("Database error while updating user card %s: %s", card_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user card.",
        ) from exc


@router.delete(
    "/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user business card",
)
async def delete_user_card(
    card_id: str,
    owner_user_id: str = Depends(get_current_user_id),
    user_card_service: UserCardService = Depends(get_user_card_service),
) -> None:
    try:
        await user_card_service.delete(owner_user_id, card_id)
    except UserCardNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CardPersistenceError as exc:
        logger.error("Database error while deleting user card %s: %s", card_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user card.",
        ) from exc
