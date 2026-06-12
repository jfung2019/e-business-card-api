from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "E-Business Card API"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    mongo_uri: str = "mongodb://mongodb:27017"
    mongo_db_name: str = "e_business_card"
    mongo_cards_collection: str = "captured_cards"
    mongo_user_cards_collection: str = "user_cards"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemini-2.5-flash"
    openrouter_timeout_seconds: float = 30.0
    openrouter_max_retries: int = 2

    firebase_credentials_path: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
