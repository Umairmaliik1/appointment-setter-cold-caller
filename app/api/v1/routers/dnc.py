"""DNC endpoints."""

from typing import Dict

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps.auth import get_current_user_from_token, require_app_access
from app.api.v1.schemas.dnc import DncUploadResponse
from app.services.dnc_service import dnc_service

router = APIRouter(prefix="/cold-caller/dnc", tags=["cold-caller-dnc"], dependencies=[Depends(require_app_access("appointment_setter"))])


@router.post("/upload", response_model=DncUploadResponse)
async def upload_dnc_csv(
    tenant_id: str = Query(...),
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user_from_token),
):
    return await dnc_service.upload_dnc_csv(tenant_id=tenant_id, file=file, current_user=current_user)

