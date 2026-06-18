import secrets
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.core.exceptions import CardPersistenceError, ScanImageNotFoundError
from app.models.share_link import ShareLinkDocument, ShareLinkResponse, SharedUserCardResponse
from app.services.scan_image_service import ScanImageService


class ShareLinkNotFoundError(Exception):
    pass


class ShareLinkService:
    def __init__(
        self,
        share_links_collection: AsyncIOMotorCollection,
        user_cards_collection: AsyncIOMotorCollection,
        settings: Settings,
        scan_image_service: ScanImageService | None = None,
    ) -> None:
        self._share_links = share_links_collection
        self._user_cards = user_cards_collection
        self._settings = settings
        self._scan_images = scan_image_service

    async def create_or_get_active_link(self, owner_user_id: str, card_id: str) -> ShareLinkResponse:
        card_object_id = self._parse_object_id(card_id)
        card = await self._get_owned_card(owner_user_id, card_object_id)
        existing = await self._share_links.find_one(
            {
                "owner_user_id": owner_user_id,
                "card_id": str(card["_id"]),
                "is_active": True,
            }
        )
        if existing:
            return self._to_link_response(existing)

        now = datetime.now(UTC)
        document = ShareLinkDocument(
            token=await self._generate_unique_token(),
            owner_user_id=owner_user_id,
            card_id=str(card["_id"]),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        try:
            await self._share_links.insert_one(document.model_dump(mode="python"))
        except PyMongoError as exc:
            raise CardPersistenceError("Failed to create share link.") from exc

        return self._to_link_response(document.model_dump(mode="python"))

    async def deactivate_active_link(self, owner_user_id: str, card_id: str) -> None:
        card_object_id = self._parse_object_id(card_id)
        await self._get_owned_card(owner_user_id, card_object_id)
        try:
            await self._share_links.update_many(
                {
                    "owner_user_id": owner_user_id,
                    "card_id": str(card_object_id),
                    "is_active": True,
                },
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.now(UTC),
                    }
                },
            )
        except PyMongoError as exc:
            raise CardPersistenceError("Failed to revoke share link.") from exc

    async def resolve_shared_card(self, token: str) -> SharedUserCardResponse:
        try:
            link = await self._share_links.find_one({"token": token, "is_active": True})
        except PyMongoError as exc:
            raise CardPersistenceError("Failed to resolve share link.") from exc
        if link is None:
            raise ShareLinkNotFoundError("Shared card not found.")

        card_object_id = self._parse_object_id(link["card_id"])
        try:
            card = await self._user_cards.find_one({"_id": card_object_id})
        except PyMongoError as exc:
            raise CardPersistenceError("Failed to load shared card.") from exc
        if card is None:
            raise ShareLinkNotFoundError("Shared card not found.")

        await self._share_links.find_one_and_update(
            {"_id": link["_id"]},
            {
                "$set": {"last_viewed_at": datetime.now(UTC), "updated_at": datetime.now(UTC)},
                "$inc": {"view_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

        front_url = f"/api/v1/public/user-cards/{token}/scan-image/front"
        back_url = f"/api/v1/public/user-cards/{token}/scan-image/back"

        return SharedUserCardResponse(
            share_token=token,
            core_fields=card["core_fields"],
            custom_fields=card.get("custom_fields", {}),
            design_id=card.get("design_id", "classic"),
            design_type=card.get("design_type", "preset"),
            wallet_display=card.get("wallet_display", "classic"),
            photo_face=card.get("photo_face", "front"),
            scan_image_front_url=front_url if self._scan_front_id(card) else None,
            scan_image_back_url=back_url if self._scan_back_id(card) else None,
            updated_at=card["updated_at"],
        )

    async def get_public_scan_image(self, token: str, face: str) -> tuple[bytes, str]:
        if self._scan_images is None:
            raise ScanImageNotFoundError("Scan image storage is not configured")
        try:
            link = await self._share_links.find_one({"token": token, "is_active": True})
        except PyMongoError as exc:
            raise CardPersistenceError("Failed to resolve share link.") from exc
        if link is None:
            raise ShareLinkNotFoundError("Shared card not found.")

        card_object_id = self._parse_object_id(link["card_id"])
        try:
            card = await self._user_cards.find_one({"_id": card_object_id})
        except PyMongoError as exc:
            raise CardPersistenceError("Failed to load shared card.") from exc
        if card is None:
            raise ShareLinkNotFoundError("Shared card not found.")

        image_id = self._scan_front_id(card) if face == "front" else self._scan_back_id(card)
        if not image_id:
            raise ScanImageNotFoundError("Scan image not found.")
        return await self._scan_images.read(image_id)

    async def _generate_unique_token(self) -> str:
        for _ in range(5):
            token = secrets.token_urlsafe(24)
            existing = await self._share_links.find_one({"token": token})
            if existing is None:
                return token
        raise CardPersistenceError("Could not generate a unique share token.")

    async def _get_owned_card(self, owner_user_id: str, card_object_id: ObjectId) -> dict:
        try:
            card = await self._user_cards.find_one({"_id": card_object_id, "owner_user_id": owner_user_id})
        except PyMongoError as exc:
            raise CardPersistenceError("Failed to load user card.") from exc
        if card is None:
            raise ShareLinkNotFoundError("User card not found.")
        return card

    @staticmethod
    def _parse_object_id(value: str) -> ObjectId:
        try:
            return ObjectId(value)
        except InvalidId as exc:
            raise ShareLinkNotFoundError("Invalid card id.") from exc

    @staticmethod
    def _scan_front_id(card: dict) -> str | None:
        return card.get("scan_image_front_id") or card.get("scan_image_id")

    @staticmethod
    def _scan_back_id(card: dict) -> str | None:
        return card.get("scan_image_back_id")

    def _to_link_response(self, document: dict) -> ShareLinkResponse:
        token = document["token"]
        base = self._settings.share_public_base_url.rstrip("/")
        return ShareLinkResponse(
            token=token,
            card_id=document["card_id"],
            is_active=document.get("is_active", True),
            share_url=f"{base}/{token}",
            created_at=document["created_at"],
            updated_at=document["updated_at"],
        )
