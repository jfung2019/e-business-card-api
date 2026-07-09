"""Per-user LLM call rate limits backed by MongoDB."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument

from app.core.config import Settings, get_settings
from app.core.exceptions import LlmRateLimitExceeded

logger = logging.getLogger(__name__)

WindowType = Literal["hour", "day"]


def _window_start(now: datetime, window: WindowType) -> datetime:
    if window == "hour":
        return now.replace(minute=0, second=0, microsecond=0)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class LlmRateLimiter:
    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        *,
        hourly_limit: int,
        daily_limit: int,
    ) -> None:
        self._collection = collection
        self._hourly_limit = hourly_limit
        self._daily_limit = daily_limit

    async def consume(self, user_id: str) -> None:
        """Reserve one LLM call for the user; raises if hourly or daily cap is reached."""
        now = datetime.now(UTC)
        hour_count = await self._increment_if_under_limit(
            user_id=user_id,
            window="hour",
            window_start=_window_start(now, "hour"),
            limit=self._hourly_limit,
        )
        if hour_count is None:
            raise LlmRateLimitExceeded(
                f"Hourly LLM limit reached ({self._hourly_limit} calls/hour).",
                retry_after_seconds=self._seconds_until_next_hour(now),
            )

        day_count = await self._increment_if_under_limit(
            user_id=user_id,
            window="day",
            window_start=_window_start(now, "day"),
            limit=self._daily_limit,
        )
        if day_count is None:
            await self._decrement(
                user_id=user_id,
                window="hour",
                window_start=_window_start(now, "hour"),
            )
            raise LlmRateLimitExceeded(
                f"Daily LLM limit reached ({self._daily_limit} calls/day).",
                retry_after_seconds=self._seconds_until_next_day(now),
            )

        logger.debug(
            "LLM quota consumed for user %s (hour=%s/%s, day=%s/%s)",
            user_id,
            hour_count,
            self._hourly_limit,
            day_count,
            self._daily_limit,
        )

    async def _increment_if_under_limit(
        self,
        *,
        user_id: str,
        window: WindowType,
        window_start: datetime,
        limit: int,
    ) -> int | None:
        filter_doc = {
            "user_id": user_id,
            "window": window,
            "window_start": window_start,
            "$or": [
                {"count": {"$lt": limit}},
                {"count": {"$exists": False}},
            ],
        }
        updated = await self._collection.find_one_and_update(
            filter_doc,
            {
                "$inc": {"count": 1},
                "$setOnInsert": {
                    "user_id": user_id,
                    "window": window,
                    "window_start": window_start,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            return None
        count = int(updated.get("count", 0))
        if count > limit:
            await self._decrement(
                user_id=user_id,
                window=window,
                window_start=window_start,
            )
            return None
        return count

    async def _decrement(
        self,
        *,
        user_id: str,
        window: WindowType,
        window_start: datetime,
    ) -> None:
        await self._collection.update_one(
            {
                "user_id": user_id,
                "window": window,
                "window_start": window_start,
                "count": {"$gt": 0},
            },
            {"$inc": {"count": -1}},
        )

    @staticmethod
    def _seconds_until_next_hour(now: datetime) -> int:
        from datetime import timedelta

        hour_floor = now.replace(minute=0, second=0, microsecond=0)
        next_hour = hour_floor + timedelta(hours=1)
        return max(1, int((next_hour - now).total_seconds()))

    @staticmethod
    def _seconds_until_next_day(now: datetime) -> int:
        from datetime import timedelta

        next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return max(1, int((next_day - now).total_seconds()))


def build_llm_rate_limiter(
    collection: AsyncIOMotorCollection,
    settings: Settings | None = None,
) -> LlmRateLimiter:
    resolved = settings or get_settings()
    return LlmRateLimiter(
        collection,
        hourly_limit=resolved.llm_rate_limit_per_hour,
        daily_limit=resolved.llm_rate_limit_per_day,
    )
