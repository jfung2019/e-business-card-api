from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.card import CoreFields, PhotoFace, WalletDisplay
from app.models.user_card import DesignType


class ShareLinkDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=16)
    owner_user_id: str = Field(..., min_length=1)
    card_id: str = Field(..., min_length=1)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    last_viewed_at: datetime | None = None
    view_count: int = 0


class ShareLinkResponse(BaseModel):
    token: str
    card_id: str
    is_active: bool
    share_url: str
    created_at: datetime
    updated_at: datetime


class SharedUserCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_token: str
    core_fields: CoreFields
    custom_fields: dict[str, str] = Field(default_factory=dict)
    design_id: str = "classic"
    design_type: DesignType = DesignType.PRESET
    wallet_display: WalletDisplay = "classic"
    photo_face: PhotoFace = "front"
    scan_image_front_url: str | None = None
    scan_image_back_url: str | None = None
    updated_at: datetime
