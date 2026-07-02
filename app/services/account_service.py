import logging

from firebase_admin import auth as firebase_auth
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import PyMongoError

from app.core.exceptions import CardPersistenceError
from app.services.scan_image_service import ScanImageService

logger = logging.getLogger(__name__)


def _scan_image_ids(document: dict) -> set[str]:
    return {
        image_id
        for image_id in (
            document.get("scan_image_id"),
            document.get("scan_image_front_id"),
            document.get("scan_image_back_id"),
        )
        if image_id
    }


class AccountService:
    def __init__(
        self,
        *,
        captured_cards: AsyncIOMotorCollection,
        user_cards: AsyncIOMotorCollection,
        share_links: AsyncIOMotorCollection,
        scan_image_service: ScanImageService,
    ) -> None:
        self._captured_cards = captured_cards
        self._user_cards = user_cards
        self._share_links = share_links
        self._scan_images = scan_image_service

    async def delete_account(self, owner_user_id: str) -> None:
        try:
            await self._delete_user_data(owner_user_id)
        except PyMongoError as exc:
            logger.exception("MongoDB delete failed for account %s", owner_user_id)
            raise CardPersistenceError("Failed to delete account data.") from exc

        try:
            firebase_auth.delete_user(owner_user_id)
        except firebase_auth.UserNotFoundError:
            logger.warning("Firebase user %s not found during account deletion", owner_user_id)
        except Exception as exc:
            logger.exception("Firebase user delete failed for %s", owner_user_id)
            raise CardPersistenceError("Failed to delete authentication account.") from exc

    async def _delete_user_data(self, owner_user_id: str) -> None:
        scan_image_ids: set[str] = set()

        for collection in (self._captured_cards, self._user_cards):
            async for document in collection.find({"owner_user_id": owner_user_id}):
                scan_image_ids.update(_scan_image_ids(document))

        for scan_image_id in scan_image_ids:
            try:
                await self._scan_images.delete(scan_image_id)
            except CardPersistenceError:
                logger.warning(
                    "Failed to delete scan image %s for user %s",
                    scan_image_id,
                    owner_user_id,
                )

        await self._scan_images.delete_for_owner(owner_user_id)

        await self._share_links.delete_many({"owner_user_id": owner_user_id})
        await self._captured_cards.delete_many({"owner_user_id": owner_user_id})
        await self._user_cards.delete_many({"owner_user_id": owner_user_id})
