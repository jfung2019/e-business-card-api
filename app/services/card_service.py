import logging
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.core.exceptions import CardNotFoundError, CardPersistenceError, ScanImageNotFoundError
from app.models.card import CapturedCardDocument, CapturedCardResponse, PhotoFace, WalletDisplay
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
        scan_image_back_bytes: bytes | None = None,
        scan_image_back_content_type: str = "image/jpeg",
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
        scan_image_front_id: str | None = None
        scan_image_back_id: str | None = None
        wallet_display: WalletDisplay = "classic"
        photo_face: PhotoFace = "front"

        if scan_image_bytes:
            if self._scan_images is None:
                raise CardPersistenceError("Scan image storage is not configured")
            scan_image_front_id = await self._scan_images.save(
                owner_user_id=owner_user_id,
                card_id=card_id,
                data=scan_image_bytes,
                content_type=scan_image_content_type,
            )
            scan_image_id = scan_image_front_id
            if scan_image_back_bytes:
                scan_image_back_id = await self._scan_images.save(
                    owner_user_id=owner_user_id,
                    card_id=card_id,
                    data=scan_image_back_bytes,
                    content_type=scan_image_back_content_type,
                )
            wallet_display = "photo"
            try:
                await self._collection.update_one(
                    {"_id": insert_result.inserted_id},
                    {
                        "$set": {
                            "scan_image_id": scan_image_id,
                            "scan_image_front_id": scan_image_front_id,
                            "scan_image_back_id": scan_image_back_id,
                            "wallet_display": wallet_display,
                            "photo_face": photo_face,
                        }
                    },
                )
            except PyMongoError as exc:
                logger.exception("Failed to link scan image to card %s", card_id)
                raise CardPersistenceError("Failed to persist captured card") from exc

        return self._to_response(
            {
                **validated_payload,
                "_id": insert_result.inserted_id,
                "scan_image_id": scan_image_id,
                "scan_image_front_id": scan_image_front_id,
                "scan_image_back_id": scan_image_back_id,
                "wallet_display": wallet_display,
                "photo_face": photo_face,
            }
        )

    async def import_from_user_card(
        self,
        owner_user_id: str,
        *,
        core_fields: dict,
        custom_fields: dict,
        source_scan_front_id: str | None,
        source_scan_back_id: str | None,
        wallet_display: str = "classic",
        photo_face: str = "front",
    ) -> CapturedCardResponse:
        document = CapturedCardDocument(
            owner_user_id=owner_user_id,
            scanned_at=datetime.now(UTC),
            core_fields=core_fields,
            custom_fields=custom_fields,
        )

        try:
            validated_payload = document.model_dump(mode="python")
            insert_result = await self._collection.insert_one(validated_payload)
        except ValidationError as exc:
            logger.exception("Imported card failed validation before persistence")
            raise CardPersistenceError("Card document failed validation") from exc
        except PyMongoError as exc:
            logger.exception("MongoDB insert failed for imported card")
            raise CardPersistenceError("Failed to persist captured card") from exc

        card_id = str(insert_result.inserted_id)
        scan_image_id: str | None = None
        scan_image_front_id: str | None = None
        scan_image_back_id: str | None = None
        resolved_wallet_display: WalletDisplay = (
            wallet_display if wallet_display in ("photo", "classic") else "classic"
        )
        resolved_photo_face: PhotoFace = photo_face if photo_face in ("front", "back") else "front"

        if source_scan_front_id:
            if self._scan_images is None:
                raise CardPersistenceError("Scan image storage is not configured")
            scan_image_front_id = await self._copy_scan_image(
                owner_user_id=owner_user_id,
                card_id=card_id,
                source_file_id=source_scan_front_id,
            )
            scan_image_id = scan_image_front_id
            if source_scan_back_id:
                scan_image_back_id = await self._copy_scan_image(
                    owner_user_id=owner_user_id,
                    card_id=card_id,
                    source_file_id=source_scan_back_id,
                )
            resolved_wallet_display = "photo"
            try:
                await self._collection.update_one(
                    {"_id": insert_result.inserted_id},
                    {
                        "$set": {
                            "scan_image_id": scan_image_id,
                            "scan_image_front_id": scan_image_front_id,
                            "scan_image_back_id": scan_image_back_id,
                            "wallet_display": resolved_wallet_display,
                            "photo_face": resolved_photo_face,
                        }
                    },
                )
            except PyMongoError as exc:
                logger.exception("Failed to link scan images to imported card %s", card_id)
                raise CardPersistenceError("Failed to persist captured card") from exc

        return self._to_response(
            {
                **validated_payload,
                "_id": insert_result.inserted_id,
                "scan_image_id": scan_image_id,
                "scan_image_front_id": scan_image_front_id,
                "scan_image_back_id": scan_image_back_id,
                "wallet_display": resolved_wallet_display,
                "photo_face": resolved_photo_face,
            }
        )

    async def _copy_scan_image(
        self,
        *,
        owner_user_id: str,
        card_id: str,
        source_file_id: str,
    ) -> str:
        if self._scan_images is None:
            raise CardPersistenceError("Scan image storage is not configured")
        image_bytes, content_type = await self._scan_images.read(source_file_id)
        return await self._scan_images.save(
            owner_user_id=owner_user_id,
            card_id=card_id,
            data=image_bytes,
            content_type=content_type,
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
        wallet_display: WalletDisplay | None = None,
        photo_face: PhotoFace | None = None,
    ) -> CapturedCardResponse:
        document = await self._get_owned_card_document(card_id, owner_user_id)

        resolved_front = CardService._scan_front_image_id(document)
        next_wallet_display = wallet_display or CardService._resolve_wallet_display(document, resolved_front)
        next_photo_face = photo_face or CardService._resolve_photo_face(document)

        if next_wallet_display == "photo" and not resolved_front:
            raise CardPersistenceError("Cannot show photo display without a scan image")
        if next_photo_face == "back" and not CardService._scan_back_image_id(document):
            raise CardPersistenceError("Cannot show back photo without a back scan image")

        try:
            await self._collection.update_one(
                {"_id": document["_id"]},
                {"$set": {"wallet_display": next_wallet_display, "photo_face": next_photo_face}},
            )
        except PyMongoError as exc:
            logger.exception("Failed to update wallet display for card %s", card_id)
            raise CardPersistenceError("Failed to update wallet display") from exc

        updated = {**document, "wallet_display": next_wallet_display, "photo_face": next_photo_face}
        return self._to_response(updated)

    async def get_scan_image(
        self,
        card_id: str,
        owner_user_id: str,
        face: PhotoFace = "front",
    ) -> tuple[bytes, str]:
        document = await self._get_owned_card_document(card_id, owner_user_id)

        scan_image_id = (
            CardService._scan_front_image_id(document)
            if face == "front"
            else CardService._scan_back_image_id(document)
        )
        if not scan_image_id or self._scan_images is None:
            raise ScanImageNotFoundError("Scan image not found")

        try:
            return await self._scan_images.read(scan_image_id)
        except CardPersistenceError as exc:
            raise ScanImageNotFoundError("Scan image not found") from exc

    async def delete(self, card_id: str, owner_user_id: str) -> None:
        document = await self._get_owned_card_document(card_id, owner_user_id)

        scan_image_ids = {
            image_id
            for image_id in (
                document.get("scan_image_id"),
                document.get("scan_image_front_id"),
                document.get("scan_image_back_id"),
            )
            if image_id
        }
        if scan_image_ids and self._scan_images is not None:
            for scan_image_id in scan_image_ids:
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
    def _scan_front_image_id(document: dict) -> str | None:
        return document.get("scan_image_front_id") or document.get("scan_image_id")

    @staticmethod
    def _scan_back_image_id(document: dict) -> str | None:
        return document.get("scan_image_back_id")

    @staticmethod
    def _scan_front_image_url(card_id: str, scan_image_front_id: str | None) -> str | None:
        if not scan_image_front_id:
            return None
        return f"/api/v1/cards/{card_id}/scan-image/front"

    @staticmethod
    def _scan_back_image_url(card_id: str, scan_image_back_id: str | None) -> str | None:
        if not scan_image_back_id:
            return None
        return f"/api/v1/cards/{card_id}/scan-image/back"

    @staticmethod
    def _resolve_wallet_display(document: dict, scan_image_id: str | None) -> WalletDisplay:
        stored = document.get("wallet_display")
        if stored in ("photo", "classic"):
            return stored
        return "photo" if scan_image_id else "classic"

    @staticmethod
    def _resolve_photo_face(document: dict) -> PhotoFace:
        stored = document.get("photo_face")
        if stored in ("front", "back"):
            return stored
        return "front"

    @staticmethod
    def _to_response(document: dict) -> CapturedCardResponse:
        card_id = str(document["_id"])
        scan_image_front_id = CardService._scan_front_image_id(document)
        scan_image_back_id = CardService._scan_back_image_id(document)
        return CapturedCardResponse(
            _id=card_id,
            owner_user_id=document["owner_user_id"],
            scanned_at=document["scanned_at"],
            core_fields=document["core_fields"],
            custom_fields=document.get("custom_fields", {}),
            scan_image_url=CardService._scan_image_url(card_id, scan_image_front_id),
            scan_image_front_url=CardService._scan_front_image_url(card_id, scan_image_front_id),
            scan_image_back_url=CardService._scan_back_image_url(card_id, scan_image_back_id),
            wallet_display=CardService._resolve_wallet_display(document, scan_image_front_id),
            photo_face=CardService._resolve_photo_face(document),
        )
