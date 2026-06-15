import io
import logging

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket
from pymongo.errors import PyMongoError

from app.core.exceptions import CardPersistenceError

logger = logging.getLogger(__name__)

GRIDFS_BUCKET_NAME = "card_scans"


class ScanImageService:
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._bucket = AsyncIOMotorGridFSBucket(database, bucket_name=GRIDFS_BUCKET_NAME)

    async def save(
        self,
        *,
        owner_user_id: str,
        card_id: str,
        data: bytes,
        content_type: str,
    ) -> str:
        try:
            file_id = await self._bucket.upload_from_stream(
                f"{card_id}.jpg",
                io.BytesIO(data),
                metadata={
                    "owner_user_id": owner_user_id,
                    "card_id": card_id,
                    "content_type": content_type,
                },
            )
        except PyMongoError as exc:
            logger.exception("GridFS upload failed for card %s", card_id)
            raise CardPersistenceError("Failed to save scan image") from exc

        return str(file_id)

    async def read(self, file_id: str) -> tuple[bytes, str]:
        try:
            object_id = ObjectId(file_id)
        except InvalidId as exc:
            raise CardPersistenceError("Invalid scan image id") from exc

        try:
            grid_out = await self._bucket.open_download_stream(object_id)
            payload = await grid_out.read()
        except PyMongoError as exc:
            logger.exception("GridFS read failed for file %s", file_id)
            raise CardPersistenceError("Failed to load scan image") from exc

        metadata = grid_out.metadata or {}
        content_type = metadata.get("content_type", "image/jpeg")
        return payload, content_type
