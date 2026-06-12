from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CoreFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Contact full name")
    company_name: str | None = None
    job_title: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    website: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        return stripped


class CapturedCardBase(BaseModel):
    """Hybrid schema shared by LLM output and persisted documents."""

    model_config = ConfigDict(extra="forbid")

    core_fields: CoreFields
    custom_fields: dict[str, str] = Field(default_factory=dict)

    @field_validator("custom_fields")
    @classmethod
    def normalize_custom_fields(cls, value: dict[str, Any]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, raw in value.items():
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                normalized[str(key).strip()] = text
        return normalized


class CapturedCardDocument(CapturedCardBase):
    owner_user_id: str = Field(..., min_length=1)
    scanned_at: datetime


class CapturedCardResponse(CapturedCardDocument):
    id: str = Field(..., alias="_id")

    model_config = ConfigDict(populate_by_name=True)
