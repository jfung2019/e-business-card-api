import logging
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.core.exceptions import CardPersistenceError
from app.models.user_card import (
    DesignType,
    UserCardCreate,
    UserCardDocument,
    UserCardResponse,
    UserCardUpdate,
)
from app.services.openrouter import OpenRouterService

logger = logging.getLogger(__name__)


class UserCardNotFoundError(Exception):
    pass


class UserCardService:
    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        openrouter_service: OpenRouterService | None = None,
    ) -> None:
        self._collection = collection
        self._openrouter = openrouter_service or OpenRouterService()

    async def list_for_user(self, owner_user_id: str) -> list[UserCardResponse]:
        try:
            cursor = self._collection.find({"owner_user_id": owner_user_id}).sort(
                [("is_primary", -1), ("sort_order", 1)],
            )
            documents = await cursor.to_list(length=None)
        except PyMongoError as exc:
            logger.exception("MongoDB query failed for user cards")
            raise CardPersistenceError("Failed to load user cards.") from exc

        return [self._to_response(document) for document in documents]

    async def create(self, owner_user_id: str, payload: UserCardCreate) -> UserCardResponse:
        now = datetime.now(UTC)
        existing_count = await self._collection.count_documents({"owner_user_id": owner_user_id})
        make_primary = payload.is_primary or existing_count == 0

        if make_primary:
            await self._clear_primary(owner_user_id)

        sort_order = 0
        if not make_primary:
            sort_order = await self._next_sort_order(owner_user_id)

        document = UserCardDocument(
            owner_user_id=owner_user_id,
            core_fields=payload.core_fields,
            custom_fields=payload.custom_fields,
            design_id=payload.design_id,
            design_type=payload.design_type,
            custom_background_url=payload.custom_background_url,
            is_primary=make_primary,
            sort_order=sort_order,
            created_at=now,
            updated_at=now,
        )

        return await self._insert_document(document)

    async def update(
        self,
        owner_user_id: str,
        card_id: str,
        payload: UserCardUpdate,
    ) -> UserCardResponse:
        object_id = self._parse_object_id(card_id)
        existing = await self._get_owned_document(owner_user_id, object_id)

        updates: dict = {"updated_at": datetime.now(UTC)}
        payload_data = payload.model_dump(exclude_unset=True)

        if "is_primary" in payload_data and payload_data["is_primary"]:
            await self._clear_primary(owner_user_id)
            updates["is_primary"] = True
            updates["sort_order"] = 0
            payload_data.pop("is_primary", None)

        for key, value in payload_data.items():
            updates[key] = value

        try:
            result = await self._collection.find_one_and_update(
                {"_id": object_id, "owner_user_id": owner_user_id},
                {"$set": updates},
                return_document=True,
            )
        except PyMongoError as exc:
            logger.exception("MongoDB update failed for user card %s", card_id)
            raise CardPersistenceError("Failed to update user card.") from exc

        if result is None:
            raise UserCardNotFoundError(f"User card {card_id} not found.")

        if payload.is_primary is False and existing.get("is_primary"):
            await self._ensure_primary_exists(owner_user_id)

        return self._to_response(result)

    async def delete(self, owner_user_id: str, card_id: str) -> None:
        object_id = self._parse_object_id(card_id)
        existing = await self._get_owned_document(owner_user_id, object_id)
        was_primary = existing.get("is_primary", False)

        try:
            result = await self._collection.delete_one(
                {"_id": object_id, "owner_user_id": owner_user_id},
            )
        except PyMongoError as exc:
            logger.exception("MongoDB delete failed for user card %s", card_id)
            raise CardPersistenceError("Failed to delete user card.") from exc

        if result.deleted_count == 0:
            raise UserCardNotFoundError(f"User card {card_id} not found.")

        if was_primary:
            await self._promote_next_primary(owner_user_id)

    async def reorder(self, owner_user_id: str, ordered_ids: list[str]) -> list[UserCardResponse]:
        object_ids = [self._parse_object_id(card_id) for card_id in ordered_ids]

        try:
            existing = await self._collection.find(
                {"owner_user_id": owner_user_id},
            ).to_list(length=None)
        except PyMongoError as exc:
            logger.exception("MongoDB query failed while reordering user cards")
            raise CardPersistenceError("Failed to reorder user cards.") from exc

        if len(existing) != len(ordered_ids):
            raise CardPersistenceError("Reorder must include every user card exactly once.")

        existing_ids = {str(document["_id"]) for document in existing}
        if set(ordered_ids) != existing_ids:
            raise CardPersistenceError("Reorder contains invalid or duplicate card ids.")

        now = datetime.now(UTC)
        try:
            for index, object_id in enumerate(object_ids):
                await self._collection.update_one(
                    {"_id": object_id, "owner_user_id": owner_user_id},
                    {
                        "$set": {
                            "sort_order": index,
                            "is_primary": index == 0,
                            "updated_at": now,
                        },
                    },
                )
        except PyMongoError as exc:
            logger.exception("MongoDB update failed while reordering user cards")
            raise CardPersistenceError("Failed to reorder user cards.") from exc

        return await self.list_for_user(owner_user_id)

    async def parse_preview(self, raw_ocr_text: str):
        return await self._openrouter.parse_ocr_text(raw_ocr_text)

    async def _insert_document(self, document: UserCardDocument) -> UserCardResponse:
        try:
            validated_payload = document.model_dump(mode="python")
            insert_result = await self._collection.insert_one(validated_payload)
        except ValidationError as exc:
            logger.exception("User card failed Pydantic validation before persistence")
            raise CardPersistenceError("User card document failed validation.") from exc
        except PyMongoError as exc:
            logger.exception("MongoDB insert failed for user card")
            raise CardPersistenceError("Failed to persist user card.") from exc

        return self._to_response({**validated_payload, "_id": insert_result.inserted_id})

    async def _get_owned_document(self, owner_user_id: str, object_id: ObjectId) -> dict:
        try:
            document = await self._collection.find_one(
                {"_id": object_id, "owner_user_id": owner_user_id},
            )
        except PyMongoError as exc:
            logger.exception("MongoDB query failed for user card lookup")
            raise CardPersistenceError("Failed to load user card.") from exc

        if document is None:
            raise UserCardNotFoundError(f"User card {object_id} not found.")
        return document

    async def _clear_primary(self, owner_user_id: str) -> None:
        await self._collection.update_many(
            {"owner_user_id": owner_user_id, "is_primary": True},
            {"$set": {"is_primary": False, "updated_at": datetime.now(UTC)}},
        )

    async def _next_sort_order(self, owner_user_id: str) -> int:
        document = await self._collection.find_one(
            {"owner_user_id": owner_user_id},
            sort=[("sort_order", -1)],
        )
        if document is None:
            return 0
        return int(document.get("sort_order", 0)) + 1

    async def _promote_next_primary(self, owner_user_id: str) -> None:
        next_card = await self._collection.find_one(
            {"owner_user_id": owner_user_id},
            sort=[("sort_order", 1)],
        )
        if next_card is None:
            return

        now = datetime.now(UTC)
        await self._collection.update_one(
            {"_id": next_card["_id"]},
            {"$set": {"is_primary": True, "sort_order": 0, "updated_at": now}},
        )

    async def _ensure_primary_exists(self, owner_user_id: str) -> None:
        primary = await self._collection.find_one(
            {"owner_user_id": owner_user_id, "is_primary": True},
        )
        if primary is None:
            await self._promote_next_primary(owner_user_id)

    @staticmethod
    def _parse_object_id(card_id: str) -> ObjectId:
        try:
            return ObjectId(card_id)
        except InvalidId as exc:
            raise UserCardNotFoundError(f"Invalid user card id: {card_id}") from exc

    @staticmethod
    def _to_response(document: dict) -> UserCardResponse:
        design_type = document.get("design_type", DesignType.PRESET)
        if isinstance(design_type, str):
            design_type = DesignType(design_type)

        return UserCardResponse(
            _id=str(document["_id"]),
            owner_user_id=document["owner_user_id"],
            core_fields=document["core_fields"],
            custom_fields=document.get("custom_fields", {}),
            design_id=document.get("design_id", "classic"),
            design_type=design_type,
            custom_background_url=document.get("custom_background_url"),
            is_primary=document.get("is_primary", False),
            sort_order=document.get("sort_order", 0),
            created_at=document["created_at"],
            updated_at=document["updated_at"],
        )
