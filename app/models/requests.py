from pydantic import BaseModel, Field


class ProcessCardRequest(BaseModel):
    raw_ocr_text: str = Field(..., min_length=1, description="Raw OCR text from on-device extraction")
