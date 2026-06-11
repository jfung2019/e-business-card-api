import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.core.exceptions import CardPersistenceError
from app.models.card import CapturedCardDocument, CapturedCardResponse
from app.services.openrouter import OpenRouterService

logger = logging.getLogger(__name__)


class CardService:
    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        openrouter_service: OpenRouterService | None = None,
    ) -> None:
        self._collection = collection
        self._openrouter = openrouter_service or OpenRouterService()

    async def process_and_save(self, owner_user_id: str, raw_ocr_text: str) -> CapturedCardResponse:
        parsed = await self._openrouter.parse_ocr_text(raw_ocr_text)

        document = CapturedCardDocument(
            owner_user_id=owner_user_id,
            scanned_at=datetime.now(UTC),
            core_fields=parsed.core_fields,
            custom_fields=parsed.custom_fields,
        )

        try:
            validated_payload = document.model_dump(mode="python")
            insert_result = await self._collection.insert_one(validated_payload)
        except ValidationError as exc:
            logger.exception("Captured card failed Pydantic validation before persistence")
            raise CardPersistenceError("Card document failed validation") from exc
        except PyMongoError as exc:
            logger.exception("MongoDB insert failed for captured card")
            raise CardPersistenceError("Failed to persist captured card") from exc

        return self._to_response({**validated_payload, "_id": insert_result.inserted_id})

    async def list_for_user(self, owner_user_id: str) -> list[CapturedCardResponse]:
        try:
            cursor = self._collection.find({"owner_user_id": owner_user_id}).sort(
                "scanned_at",
                -1,
            )
            documents = await cursor.to_list(length=None)
        except PyMongoError as exc:
            logger.exception("MongoDB query failed for captured cards")
            raise CardPersistenceError("Failed to load captured cards") from exc

        return [self._to_response(document) for document in documents]

    @staticmethod
    def _to_response(document: dict) -> CapturedCardResponse:
        return CapturedCardResponse(
            _id=str(document["_id"]),
            owner_user_id=document["owner_user_id"],
            scanned_at=document["scanned_at"],
            core_fields=document["core_fields"],
            custom_fields=document.get("custom_fields", {}),
        )
