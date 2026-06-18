from collections.abc import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.core.config import Settings, get_settings
from app.services.scan_image_service import ScanImageService

_client: AsyncIOMotorClient | None = None


def get_motor_client(settings: Settings | None = None) -> AsyncIOMotorClient:
    global _client
    resolved = settings or get_settings()
    if _client is None:
        _client = AsyncIOMotorClient(resolved.mongo_uri)
    return _client


def get_database(settings: Settings | None = None) -> AsyncIOMotorDatabase:
    resolved = settings or get_settings()
    return get_motor_client(resolved)[resolved.mongo_db_name]


def get_cards_collection(settings: Settings | None = None) -> AsyncIOMotorCollection:
    resolved = settings or get_settings()
    return get_database(resolved)[resolved.mongo_cards_collection]


async def close_motor_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_user_cards_collection(settings: Settings | None = None) -> AsyncIOMotorCollection:
    resolved = settings or get_settings()
    return get_database(resolved)[resolved.mongo_user_cards_collection]


def get_share_links_collection(settings: Settings | None = None) -> AsyncIOMotorCollection:
    resolved = settings or get_settings()
    return get_database(resolved)[resolved.mongo_share_links_collection]


async def get_cards_collection_dependency() -> AsyncGenerator[AsyncIOMotorCollection, None]:
    yield get_cards_collection()


async def get_user_cards_collection_dependency() -> AsyncGenerator[AsyncIOMotorCollection, None]:
    yield get_user_cards_collection()


async def get_share_links_collection_dependency() -> AsyncGenerator[AsyncIOMotorCollection, None]:
    yield get_share_links_collection()


async def get_scan_image_service_dependency() -> AsyncGenerator[ScanImageService, None]:
    yield ScanImageService(get_database())
