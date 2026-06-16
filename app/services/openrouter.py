import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import OpenRouterError, OpenRouterTimeoutError
from app.models.card import CapturedCardBase

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You extract structured contact data from raw OCR text of physical business cards.

Return ONLY a valid JSON object with exactly this shape:
{
  "core_fields": {
    "name": "string (required)",
    "company_name": "string or null",
    "job_title": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "website": "string or null"
  },
  "custom_fields": {
    "FieldLabel": "value"
  }
}

Rules:
- Put standard fields in core_fields (including job_title for role/position). Put everything else (fax, address, social handles, etc.) in custom_fields.
- name is required. Use null for unknown core_fields values, not empty strings.
- custom_fields values must be strings. Omit empty custom_fields entries.
- Do not wrap the JSON in markdown. Do not add commentary or extra keys.
"""


class OpenRouterService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def parse_ocr_text(self, raw_ocr_text: str) -> CapturedCardBase:
        if not self._settings.openrouter_api_key:
            raise OpenRouterError("OpenRouter API key is not configured")

        payload = self._build_request_payload(raw_ocr_text)
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://e-business-card.local",
            "X-Title": self._settings.app_name,
        }

        last_error: Exception | None = None
        for attempt in range(1, self._settings.openrouter_max_retries + 2):
            try:
                async with httpx.AsyncClient(
                    base_url=self._settings.openrouter_base_url,
                    timeout=httpx.Timeout(self._settings.openrouter_timeout_seconds),
                ) as client:
                    response = await client.post(
                        "/chat/completions",
                        headers=headers,
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                last_error = OpenRouterTimeoutError(
                    f"OpenRouter request timed out after {self._settings.openrouter_timeout_seconds}s",
                )
                logger.warning(
                    "OpenRouter timeout on attempt %s/%s",
                    attempt,
                    self._settings.openrouter_max_retries + 1,
                )
                if attempt > self._settings.openrouter_max_retries:
                    raise last_error from exc
                continue
            except httpx.RequestError as exc:
                last_error = OpenRouterError(f"OpenRouter network error: {exc}")
                logger.warning(
                    "OpenRouter network error on attempt %s/%s: %s",
                    attempt,
                    self._settings.openrouter_max_retries + 1,
                    exc,
                )
                if attempt > self._settings.openrouter_max_retries:
                    raise last_error from exc
                continue

            if response.status_code >= 400:
                detail = self._extract_error_message(response)
                if self._is_transient_http_status(response.status_code):
                    last_error = OpenRouterError(
                        f"OpenRouter transient HTTP {response.status_code}: {detail}",
                        status_code=response.status_code,
                    )
                    logger.warning(
                        "OpenRouter transient HTTP %s on attempt %s/%s: %s",
                        response.status_code,
                        attempt,
                        self._settings.openrouter_max_retries + 1,
                        detail,
                    )
                    if attempt > self._settings.openrouter_max_retries:
                        raise last_error
                    await asyncio.sleep(self._retry_backoff_seconds(attempt))
                    continue
                logger.error(
                    "OpenRouter HTTP %s: %s",
                    response.status_code,
                    detail,
                )
                raise OpenRouterError(
                    f"OpenRouter returned HTTP {response.status_code}: {detail}",
                    status_code=response.status_code,
                )

            return self._parse_completion_response(response.json())

        raise last_error or OpenRouterError("OpenRouter request failed")

    @staticmethod
    def _is_transient_http_status(status_code: int) -> bool:
        return status_code in {429, 500, 502, 503, 504}

    @staticmethod
    def _retry_backoff_seconds(attempt: int) -> float:
        # Small linear backoff keeps user-facing latency bounded.
        return min(0.5 * attempt, 2.0)

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
            error = body.get("error", body)
            if isinstance(error, dict):
                return str(error.get("message", error))
            return str(error)
        except (json.JSONDecodeError, ValueError, AttributeError):
            return response.text[:200] or "Unknown error"

    def _build_request_payload(self, raw_ocr_text: str) -> dict[str, Any]:
        return {
            "model": self._settings.openrouter_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract contact data from this OCR text:\n\n{raw_ocr_text}",
                },
            ],
        }

    def _parse_completion_response(self, body: dict[str, Any]) -> CapturedCardBase:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError("OpenRouter response missing message content") from exc

        if isinstance(content, dict):
            parsed = content
        else:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise OpenRouterError("OpenRouter returned invalid JSON") from exc

        try:
            return CapturedCardBase.model_validate(parsed)
        except Exception as exc:
            raise OpenRouterError(f"OpenRouter JSON failed schema validation: {exc}") from exc
