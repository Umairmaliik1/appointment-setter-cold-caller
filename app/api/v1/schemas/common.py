"""Common schemas."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class MessageResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None


class PaginationParams(BaseModel):
    limit: int = 100
    offset: int = 0


class RuntimeEventResponse(BaseModel):
    id: str
    campaign_id: str
    tenant_id: str
    event_type: str
    message: str
    metadata: Dict[str, Any]
    created_at: datetime

