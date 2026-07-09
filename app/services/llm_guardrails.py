"""Guardrails for OCR-to-LLM parsing: prompt-injection resistance and output bounds."""

from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import OpenRouterSafetyError

_OCR_TAG_PATTERN = re.compile(r"</?ocr>", re.IGNORECASE)

# Instruction-override phrases seen in jailbreak / chatbot abuse (e.g. "ignore rules, write Python").
_INSTRUCTION_OVERRIDE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|prompts?)",
        r"disregard\s+(all\s+)?(previous|prior|above)",
        r"forget\s+(all\s+)?(previous|prior|above)",
        r"you\s+are\s+now\b",
        r"act\s+as\b",
        r"pretend\s+(you\s+are|to\s+be)\b",
        r"new\s+instructions?\s*:",
        r"system\s+prompt\s*:",
        r"write\s+(me\s+)?(a\s+)?(python|javascript|java|typescript|bash|shell|sql)\b",
        r"generate\s+(some\s+)?(code|script|program)\b",
        r"show\s+me\s+(the\s+)?(code|script|source)\b",
        r"```",
    )
)

# Code-like content should never appear in extracted contact field values.
_CODE_OUTPUT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    for pattern in (
        r"^\s*```",
        r"\bimport\s+\w+",
        r"\bfrom\s+\w+\s+import\b",
        r"\bdef\s+\w+\s*\(",
        r"\bfunction\s+\w+\s*\(",
        r"\bconsole\.log\s*\(",
        r"\bpublic\s+static\s+void\s+main\b",
        r"<\?php\b",
        r"#!/(?:usr/bin/)?",
    )
)

# Loose signals that OCR text plausibly came from a business card.
_CARD_LIKE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"[@]",
        r"\b\d{3,}\b",
        r"\b(?:tel|phone|mobile|fax|email|www\.|https?://)\b",
        r"\b(?:ltd|limited|inc|corp|company|co\.)\b",
        r"[\u4e00-\u9fff]{2,}",
    )
)


def sanitize_ocr_text(raw_ocr_text: str, *, max_length: int) -> str:
    """Normalize OCR input and prevent delimiter breakout in the LLM user message."""
    text = raw_ocr_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = _OCR_TAG_PATTERN.sub("", text)
    if len(text) > max_length:
        text = text[:max_length]
    return text


def _looks_like_business_card_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _CARD_LIKE_PATTERNS)


def _instruction_override_count(text: str) -> int:
    return sum(1 for pattern in _INSTRUCTION_OVERRIDE_PATTERNS if pattern.search(text))


def validate_ocr_submission(raw_ocr_text: str, *, max_length: int, max_lines: int) -> str:
    """Reject oversized OCR payloads (e.g. pasted PDF text) before persistence or LLM calls."""
    text = sanitize_ocr_text(raw_ocr_text, max_length=max_length)
    if not text:
        raise OpenRouterSafetyError("OCR text is empty")
    if text.count("\n") + 1 > max_lines:
        raise OpenRouterSafetyError("OCR text exceeds business card size limits")
    return text


def validate_ocr_input(raw_ocr_text: str, *, max_length: int, max_lines: int) -> str:
    """Reject obvious prompt-injection payloads before calling the LLM."""
    text = validate_ocr_submission(raw_ocr_text, max_length=max_length, max_lines=max_lines)

    override_hits = _instruction_override_count(text)
    if override_hits == 0:
        return text

    # Allow job titles like "Python Developer" when the scan still looks like a card.
    if _looks_like_business_card_text(text) and override_hits <= 1:
        return text

    raise OpenRouterSafetyError("OCR text failed safety validation")


def _value_looks_like_code(value: str) -> bool:
    return any(pattern.search(value) for pattern in _CODE_OUTPUT_PATTERNS)


def validate_parsed_fields(
    payload: dict[str, Any],
    *,
    max_custom_fields: int,
    max_field_value_length: int,
) -> dict[str, Any]:
    """Ensure LLM output stays within business-card bounds and contains no code."""
    core_raw = payload.get("core_fields")
    if not isinstance(core_raw, dict):
        raise OpenRouterSafetyError("LLM output failed safety validation")

    custom_raw = payload.get("custom_fields")
    custom: dict[str, Any] = custom_raw if isinstance(custom_raw, dict) else {}

    if len(custom) > max_custom_fields:
        raise OpenRouterSafetyError("LLM output failed safety validation")

    for section_name, fields in (("core_fields", core_raw), ("custom_fields", custom)):
        if not isinstance(fields, dict):
            raise OpenRouterSafetyError("LLM output failed safety validation")
        for key, raw in fields.items():
            if raw is None:
                continue
            text = str(raw).strip()
            if not text:
                continue
            if len(text) > max_field_value_length:
                raise OpenRouterSafetyError("LLM output failed safety validation")
            if _value_looks_like_code(text):
                raise OpenRouterSafetyError("LLM output failed safety validation")
            if section_name == "core_fields" and str(key).strip() == "name":
                if _instruction_override_count(text) > 0:
                    raise OpenRouterSafetyError("LLM output failed safety validation")

    return payload
