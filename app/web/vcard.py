import re

from app.models.share_link import SharedUserCardResponse


def _escape_vcard(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"[-\s]+", "-", cleaned)
    return cleaned or "contact"


def build_vcard(card: SharedUserCardResponse) -> tuple[str, str]:
    core = card.core_fields
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{_escape_vcard(core.name)}",
    ]

    if core.company_name:
        lines.append(f"ORG:{_escape_vcard(core.company_name)}")
    if core.job_title:
        lines.append(f"TITLE:{_escape_vcard(core.job_title)}")
    if core.email:
        lines.append(f"EMAIL;TYPE=INTERNET:{core.email}")
    if core.phone:
        lines.append(f"TEL;TYPE=CELL:{_escape_vcard(core.phone)}")
    if core.website:
        lines.append(f"URL:{_escape_vcard(core.website)}")

    if card.custom_fields:
        note_parts = [f"{key}: {value}" for key, value in card.custom_fields.items()]
        lines.append(f"NOTE:{_escape_vcard(chr(10).join(note_parts))}")

    lines.append("END:VCARD")
    filename = f"{_safe_filename(core.name)}.vcf"
    return "\r\n".join(lines) + "\r\n", filename
