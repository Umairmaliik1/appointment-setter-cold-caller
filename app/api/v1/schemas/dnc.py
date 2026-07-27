"""DNC schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field


class DncUploadResponse(BaseModel):
    tenant_id: str
    accepted_count: int
    ignored_count: int
    total_rows: int
    ignored_numbers: List[str]


class DncEntryResponse(BaseModel):
    id: str
    tenant_id: str
    phone_number: str
    source: str
    created_by: str
    created_at: str


class DncCreateRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    phone_number: str = Field(..., min_length=3, max_length=32)
    source: str = Field(default="manual", max_length=64)

