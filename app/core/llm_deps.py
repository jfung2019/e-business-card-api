from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.auth import get_current_user_id
from app.core.exceptions import LlmRateLimitExceeded
from app.db.mongodb import get_llm_rate_limits_collection_dependency
from app.services.llm_rate_limiter import LlmRateLimiter, build_llm_rate_limiter


async def get_llm_rate_limiter(
    collection: AsyncIOMotorCollection = Depends(get_llm_rate_limits_collection_dependency),
) -> AsyncGenerator[LlmRateLimiter, None]:
    yield build_llm_rate_limiter(collection)


async def enforce_llm_rate_limit(
    user_id: str = Depends(get_current_user_id),
    rate_limiter: LlmRateLimiter = Depends(get_llm_rate_limiter),
) -> str:
    try:
        await rate_limiter.consume(user_id)
    except LlmRateLimitExceeded as exc:
        headers = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many card parsing requests. Please try again later.",
            headers=headers,
        ) from exc
    return user_id
