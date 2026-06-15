from pydantic import BaseModel, Field

from app.models.card import WalletDisplay


class ProcessCardRequest(BaseModel):
    raw_ocr_text: str = Field(..., min_length=1, description="Raw OCR text from on-device extraction")


class UpdateWalletDisplayRequest(BaseModel):
    wallet_display: WalletDisplay
