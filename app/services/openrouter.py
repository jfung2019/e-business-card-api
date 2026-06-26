import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import OpenRouterError, OpenRouterTimeoutError
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.models.card import CapturedCardBase

logger = logging.getLogger(__name__)

_CORE_FIELD_KEYS = frozenset(
    {"name", "company_name", "job_title", "email", "phone", "website"},
)
_OPTIONAL_CORE_FIELD_KEYS = frozenset(
    {"company_name", "job_title", "email", "phone", "website"},
)
_EMAIL_ADAPTER = TypeAdapter(EmailStr)

SYSTEM_PROMPT = """You extract structured contact data from raw OCR text of physical business cards.

OCR text may include a back-of-card section after a line containing only `--- BACK ---`. Treat both sides as one contact; prefer the clearest value when fields repeat.

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
        max_attempts = self._settings.openrouter_max_retries + 1
        for attempt in range(1, max_attempts + 1):
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
                if attempt >= max_attempts:
                    raise last_error from exc
                await asyncio.sleep(self._retry_backoff_seconds(attempt))
                continue
            except httpx.RequestError as exc:
                last_error = OpenRouterError(f"OpenRouter network error: {exc}")
                logger.warning(
                    "OpenRouter network error on attempt %s/%s: %s",
                    attempt,
                    self._settings.openrouter_max_retries + 1,
                    exc,
                )
                if attempt >= max_attempts:
                    raise last_error from exc
                await asyncio.sleep(self._retry_backoff_seconds(attempt))
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
                    if attempt >= max_attempts:
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

            try:
                return self._parse_completion_response(response.json())
            except OpenRouterError as exc:
                last_error = exc
                logger.warning(
                    "OpenRouter response parse failed on attempt %s/%s: %s",
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt >= max_attempts:
                    raise
                await asyncio.sleep(self._retry_backoff_seconds(attempt))
                continue

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

    @staticmethod
    def _extract_json_object(content: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(content, dict):
            return content

        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```+\s*$", "", text).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise OpenRouterError("OpenRouter returned invalid JSON")

        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise OpenRouterError("OpenRouter returned invalid JSON") from exc

        if not isinstance(parsed, dict):
            raise OpenRouterError("OpenRouter returned invalid JSON")
        return parsed

    @staticmethod
    def _coerce_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _coerce_email(cls, value: Any) -> str | None:
        text = cls._coerce_optional_text(value)
        if text is None:
            return None
        try:
            return str(_EMAIL_ADAPTER.validate_python(text))
        except (ValidationError, ValueError):
            return None

    @classmethod
    def _normalize_llm_payload(cls, parsed: dict[str, Any]) -> dict[str, Any]:
        core_raw = parsed.get("core_fields")
        if not isinstance(core_raw, dict):
            return parsed

        custom_raw = parsed.get("custom_fields")
        custom: dict[str, str] = {}
        if isinstance(custom_raw, dict):
            for key, raw in custom_raw.items():
                text = cls._coerce_optional_text(raw)
                if text:
                    custom[str(key).strip()] = text

        core: dict[str, Any] = {}
        for key, value in core_raw.items():
            key_str = str(key).strip()
            if key_str in _CORE_FIELD_KEYS:
                core[key_str] = value
            else:
                text = cls._coerce_optional_text(value)
                if text:
                    custom[key_str] = text

        for optional_key in _OPTIONAL_CORE_FIELD_KEYS:
            if optional_key not in core:
                continue
            if optional_key == "email":
                core[optional_key] = cls._coerce_email(core[optional_key])
            else:
                core[optional_key] = cls._coerce_optional_text(core[optional_key])

        name = cls._coerce_optional_text(core.get("name"))
        if name:
            core["name"] = name

        return {
            "core_fields": core,
            "custom_fields": custom,
        }

    def _parse_completion_response(self, body: dict[str, Any]) -> CapturedCardBase:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError("OpenRouter response missing message content") from exc

        try:
            parsed = self._extract_json_object(content)
            normalized = self._normalize_llm_payload(parsed)
            return CapturedCardBase.model_validate(normalized)
        except OpenRouterError:
            raise
        except Exception as exc:
            raise OpenRouterError(f"OpenRouter JSON failed schema validation: {exc}") from exc
