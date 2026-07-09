import re

_LANGUAGE_LABELS = {
    "en": "en",
    "cn": "cn",
    "ch": "cn",
    "zh": "cn",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
}

_EXACT_LABELS = {
    "phone_2": "phone 2",
    "phone_3": "phone 3",
}

_KEY_ALIASES = {
    "address_ch": "address_cn",
    "address_zh": "address_cn",
}

_LOCALIZED_KEY_PATTERN = re.compile(r"^(.+)_([a-z]{2})$", re.IGNORECASE)


def canonical_custom_field_key(key: str) -> str:
    trimmed = key.strip()
    if not trimmed:
        return trimmed
    return _KEY_ALIASES.get(trimmed.lower(), trimmed)


def format_custom_field_label(key: str) -> str:
    trimmed = canonical_custom_field_key(key.strip())
    if not trimmed:
        return trimmed

    exact = _EXACT_LABELS.get(trimmed) or _EXACT_LABELS.get(trimmed.lower())
    if exact:
        return exact

    match = _LOCALIZED_KEY_PATTERN.match(trimmed)
    if match:
        field, lang_code = match.groups()
        lang = _LANGUAGE_LABELS.get(lang_code.lower(), lang_code.lower())
        return f"{field.replace('_', ' ')} ({lang})"

    if "_" in trimmed:
        return trimmed.replace("_", " ")

    return trimmed
