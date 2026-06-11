from pydantic import BaseModel, Field


class ProcessCardRequest(BaseModel):
    owner_user_id: str = Field(..., min_length=1, description="App user who scanned the card")
    raw_ocr_text: str = Field(..., min_length=1, description="Raw OCR text from on-device extraction")
