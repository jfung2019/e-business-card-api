from pathlib import Path
from urllib.parse import urlparse

from fastapi.templating import Jinja2Templates

from app.core.config import Settings
from app.models.share_link import SharedUserCardResponse
from app.utils.custom_fields import format_custom_field_label
from app.web.card_designs import design_for_id

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def public_api_base_url(settings: Settings) -> str:
    share_base = settings.share_public_base_url.rstrip("/")
    if share_base.endswith("/c"):
        return share_base[:-2]
    parsed = urlparse(share_base)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return share_base


def absolute_public_url(settings: Settings, path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{public_api_base_url(settings).rstrip('/')}{path}"


def resolve_display_mode(card: SharedUserCardResponse) -> str:
    if card.wallet_display == "photo" and card.scan_image_front_url:
        return "photo"
    return "classic"


def company_label(card: SharedUserCardResponse) -> str:
    core = card.core_fields
    if core.company_name and core.company_name.strip():
        return core.company_name.strip()
    return core.name


def build_share_page_context(
    request,
    settings: Settings,
    card: SharedUserCardResponse,
) -> dict:
    token = card.share_token
    display_mode = resolve_display_mode(card)
    front_url = absolute_public_url(settings, card.scan_image_front_url)
    back_url = absolute_public_url(settings, card.scan_image_back_url)
    photo_face = card.photo_face if card.photo_face in {"front", "back"} else "front"
    active_photo_url = back_url if photo_face == "back" and back_url else front_url
    share_base = settings.share_public_base_url.rstrip("/")
    core = card.core_fields

    custom_fields = [
        (format_custom_field_label(key), value)
        for key, value in sorted(card.custom_fields.items(), key=lambda item: item[0].lower())
        if value.strip()
    ]

    return {
        "request": request,
        "card": card,
        "display_mode": display_mode,
        "palette": design_for_id(card.design_id),
        "company": company_label(card),
        "custom_fields": custom_fields,
        "photo_front_url": front_url,
        "photo_back_url": back_url,
        "active_photo_url": active_photo_url,
        "photo_face": photo_face,
        "has_both_faces": bool(front_url and back_url),
        "vcard_url": f"{share_base}/{token}/vcard",
        "app_url": f"ebusinesscard://c/{token}",
        "page_title": f"{core.name} — E-Business Card",
        "core_name": core.name,
        "core_company": core.company_name,
        "core_job_title": core.job_title,
        "core_email": str(core.email) if core.email else None,
        "core_phone": core.phone,
        "core_website": core.website,
    }
