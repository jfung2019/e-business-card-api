import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from motor.motor_asyncio import AsyncIOMotorCollection

from app.core.config import Settings, get_settings
from app.core.exceptions import CardPersistenceError
from app.db.mongodb import (
    get_scan_image_service_dependency,
    get_share_links_collection_dependency,
    get_user_cards_collection_dependency,
)
from app.services.scan_image_service import ScanImageService
from app.services.share_link_service import ShareLinkNotFoundError, ShareLinkService
from app.web.share_page import TEMPLATES, build_share_page_context
from app.web.vcard import build_vcard

logger = logging.getLogger(__name__)

router = APIRouter(tags=["share-web"])


def get_share_link_service(
    share_links_collection: AsyncIOMotorCollection = Depends(get_share_links_collection_dependency),
    user_cards_collection: AsyncIOMotorCollection = Depends(get_user_cards_collection_dependency),
    scan_image_service: ScanImageService = Depends(get_scan_image_service_dependency),
    settings: Settings = Depends(get_settings),
) -> ShareLinkService:
    return ShareLinkService(
        share_links_collection=share_links_collection,
        user_cards_collection=user_cards_collection,
        settings=settings,
        scan_image_service=scan_image_service,
    )


@router.get("/c/{token}", response_class=HTMLResponse, include_in_schema=False)
async def render_shared_card_page(
    request: Request,
    token: str,
    settings: Settings = Depends(get_settings),
    service: ShareLinkService = Depends(get_share_link_service),
) -> HTMLResponse:
    try:
        card = await service.resolve_shared_card(token)
    except ShareLinkNotFoundError:
        return TEMPLATES.TemplateResponse(
            request,
            "share/not_found.html",
            status_code=404,
        )
    except CardPersistenceError as exc:
        logger.error("Failed to render shared card page: %s", exc)
        return TEMPLATES.TemplateResponse(
            request,
            "share/not_found.html",
            status_code=500,
        )

    context = build_share_page_context(request, settings, card)
    return TEMPLATES.TemplateResponse(request, "share/card.html", context)


@router.get("/c/{token}/vcard", include_in_schema=False)
async def download_shared_card_vcard(
    token: str,
    service: ShareLinkService = Depends(get_share_link_service),
) -> Response:
    try:
        card = await service.resolve_shared_card(token)
    except ShareLinkNotFoundError:
        return Response(status_code=404, content="Shared card not found.")
    except CardPersistenceError as exc:
        logger.error("Failed to build vCard: %s", exc)
        return Response(status_code=500, content="Unable to build contact file.")

    vcard_body, filename = build_vcard(card)
    return Response(
        content=vcard_body,
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
