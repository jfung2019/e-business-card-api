import logging

import firebase_admin
from firebase_admin import credentials

from app.core.config import Settings

logger = logging.getLogger(__name__)


def init_firebase(settings: Settings) -> None:
    if firebase_admin._apps:
        return

    if not settings.firebase_credentials_path:
        logger.warning(
            "FIREBASE_CREDENTIALS_PATH is not set; authenticated endpoints will reject requests.",
        )
        return

    cred = credentials.Certificate(settings.firebase_credentials_path)
    firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK initialized")


def is_firebase_initialized() -> bool:
    return bool(firebase_admin._apps)
