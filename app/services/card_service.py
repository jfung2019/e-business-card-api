import logging
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.core.exceptions import CardNotFoundError, CardPersistenceError, ScanImageNotFoundError
from app.models.card import CapturedCardDocument, CapturedCardResponse, WalletDisplay
from app.services.openrouter import OpenRouterService
from app.services.scan_image_service import ScanImageService

logger = logging.getLogger(__name__)


class CardService:
    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        scan_image_service: ScanImageService | None = None,
        openrouter_service: OpenRouterService | None = None,
    ) -> None:
        self._collection = collection
        self._scan_images = scan_image_service
        self._openrouter = openrouter_service or OpenRouterService()

    async def process_and_save(
        self,
        owner_user_id: str,
        raw_ocr_text: str,
        scan_image_bytes: bytes | None = None,
        scan_image_content_type: str = "image/jpeg",
    ) -> CapturedCardResponse:
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

        card_id = str(insert_result.inserted_id)
        scan_image_id: str | None = None
        wallet_display: WalletDisplay = "classic"

        if scan_image_bytes:
            if self._scan_images is None:
                raise CardPersistenceError("Scan image storage is not configured")
            scan_image_id = await self._scan_images.save(
                owner_user_id=owner_user_id,
                card_id=card_id,
                data=scan_image_bytes,
                content_type=scan_image_content_type,
            )
            wallet_display = "photo"
            try:
                await self._collection.update_one(
                    {"_id": insert_result.inserted_id},
                    {"$set": {"scan_image_id": scan_image_id, "wallet_display": wallet_display}},
                )
            except PyMongoError as exc:
                logger.exception("Failed to link scan image to card %s", card_id)
                raise CardPersistenceError("Failed to persist captured card") from exc

        return self._to_response(
            {
                **validated_payload,
                "_id": insert_result.inserted_id,
                "scan_image_id": scan_image_id,
                "wallet_display": wallet_display,
            }
        )

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

    async def update_wallet_display(
        self,
        card_id: str,
        owner_user_id: str,
        wallet_display: WalletDisplay,
    ) -> CapturedCardResponse:
        document = await self._get_owned_card_document(card_id, owner_user_id)

        if wallet_display == "photo" and not document.get("scan_image_id"):
            raise CardPersistenceError("Cannot show photo display without a scan image")

        try:
            await self._collection.update_one(
                {"_id": document["_id"]},
                {"$set": {"wallet_display": wallet_display}},
            )
        except PyMongoError as exc:
            logger.exception("Failed to update wallet display for card %s", card_id)
            raise CardPersistenceError("Failed to update wallet display") from exc

        updated = {**document, "wallet_display": wallet_display}
        return self._to_response(updated)

    async def get_scan_image(self, card_id: str, owner_user_id: str) -> tuple[bytes, str]:
        document = await self._get_owned_card_document(card_id, owner_user_id)

        scan_image_id = document.get("scan_image_id")
        if not scan_image_id or self._scan_images is None:
            raise ScanImageNotFoundError("Scan image not found")

        try:
            return await self._scan_images.read(scan_image_id)
        except CardPersistenceError as exc:
            raise ScanImageNotFoundError("Scan image not found") from exc

    async def delete(self, card_id: str, owner_user_id: str) -> None:
        document = await self._get_owned_card_document(card_id, owner_user_id)

        scan_image_id = document.get("scan_image_id")
        if scan_image_id and self._scan_images is not None:
            try:
                await self._scan_images.delete(scan_image_id)
            except CardPersistenceError:
                logger.warning(
                    "Failed to delete scan image %s for card %s",
                    scan_image_id,
                    card_id,
                )

        try:
            result = await self._collection.delete_one(
                {"_id": document["_id"], "owner_user_id": owner_user_id},
            )
        except PyMongoError as exc:
            logger.exception("MongoDB delete failed for card %s", card_id)
            raise CardPersistenceError("Failed to delete captured card") from exc

        if result.deleted_count == 0:
            raise CardNotFoundError("Card not found")

    async def _get_owned_card_document(self, card_id: str, owner_user_id: str) -> dict:
        try:
            object_id = ObjectId(card_id)
        except InvalidId as exc:
            raise CardNotFoundError("Card not found") from exc

        try:
            document = await self._collection.find_one(
                {"_id": object_id, "owner_user_id": owner_user_id},
            )
        except PyMongoError as exc:
            logger.exception("MongoDB query failed for card %s", card_id)
            raise CardPersistenceError("Failed to load card") from exc

        if document is None:
            raise CardNotFoundError("Card not found")

        return document

    @staticmethod
    def _scan_image_url(card_id: str, scan_image_id: str | None) -> str | None:
        if not scan_image_id:
            return None
        return f"/api/v1/cards/{card_id}/scan-image"

    @staticmethod
    def _resolve_wallet_display(document: dict, scan_image_id: str | None) -> WalletDisplay:
        stored = document.get("wallet_display")
        if stored in ("photo", "classic"):
            return stored
        return "photo" if scan_image_id else "classic"

    @staticmethod
    def _to_response(document: dict) -> CapturedCardResponse:
        card_id = str(document["_id"])
        scan_image_id = document.get("scan_image_id")
        return CapturedCardResponse(
            _id=card_id,
            owner_user_id=document["owner_user_id"],
            scanned_at=document["scanned_at"],
            core_fields=document["core_fields"],
            custom_fields=document.get("custom_fields", {}),
            scan_image_url=CardService._scan_image_url(card_id, scan_image_id),
            wallet_display=CardService._resolve_wallet_display(document, scan_image_id),
        )
