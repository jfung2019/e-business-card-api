import re

_LANGUAGE_LABELS = {
    "en": "English",
    "ch": "Chinese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}

_EXACT_LABELS = {
    "address_en": "Address (English)",
    "address_ch": "Address (Chinese)",
    "address_zh": "Address (Chinese)",
    "alternate_name_en": "Alternate name (English)",
    "alternate_name_ch": "Alternate name (Chinese)",
    "alternate_name_zh": "Alternate name (Chinese)",
    "phone_2": "Phone 2",
}

_LOCALIZED_KEY_PATTERN = re.compile(r"^(.+)_([a-z]{2})$", re.IGNORECASE)


def format_custom_field_label(key: str) -> str:
    trimmed = key.strip()
    if not trimmed:
        return trimmed

    exact = _EXACT_LABELS.get(trimmed) or _EXACT_LABELS.get(trimmed.lower())
    if exact:
        return exact

    match = _LOCALIZED_KEY_PATTERN.match(trimmed)
    if match:
        field, lang_code = match.groups()
        field_label = field.replace("_", " ").title()
        language_label = _LANGUAGE_LABELS.get(lang_code.lower())
        if language_label:
            return f"{field_label} ({language_label})"

    if "_" in trimmed:
        return trimmed.replace("_", " ").title()

    return trimmed
