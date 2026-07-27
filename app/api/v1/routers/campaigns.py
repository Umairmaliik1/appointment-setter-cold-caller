"""Campaign endpoints."""

from typing import Dict, List

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps.auth import get_current_user_from_token, require_app_access
from app.api.v1.schemas.campaign import (
    CampaignAttemptResponse,
    CampaignContactResponse,
    CampaignControlResponse,
    CampaignCreateRequest,
    CampaignResponse,
    CampaignUpdateRequest,
    ContactUploadResponse,
    IntroAudioConfirmRequest,
    IntroAudioUploadUrlRequest,
    IntroAudioUploadUrlResponse,
)
from app.services.campaign_service import campaign_service

router = APIRouter(prefix="/cold-caller/campaigns", tags=["cold-caller-campaigns"], dependencies=[Depends(require_app_access("appointment_setter"))])


@router.post("", response_model=CampaignResponse)
async def create_campaign(payload: CampaignCreateRequest, current_user: Dict = Depends(get_current_user_from_token)):
    return await campaign_service.create_campaign(payload, current_user)


@router.get("", response_model=List[CampaignResponse])
async def list_campaigns(
    tenant_id: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Dict = Depends(get_current_user_from_token),
):
    return await campaign_service.list_campaigns(tenant_id=tenant_id, current_user=current_user, limit=limit, offset=offset)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    return await campaign_service.get_campaign(campaign_id, current_user)


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdateRequest,
    current_user: Dict = Depends(get_current_user_from_token),
):
    return await campaign_service.update_campaign(campaign_id, payload, current_user)


@router.post("/{campaign_id}/contacts/upload", response_model=ContactUploadResponse)
async def upload_contacts(
    campaign_id: str,
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user_from_token),
):
    return await campaign_service.upload_contacts(campaign_id=campaign_id, file=file, current_user=current_user)


@router.post("/{campaign_id}/intro-audio/upload-url", response_model=IntroAudioUploadUrlResponse)
async def create_intro_audio_upload_url(
    campaign_id: str,
    payload: IntroAudioUploadUrlRequest,
    current_user: Dict = Depends(get_current_user_from_token),
):
    return await campaign_service.create_intro_audio_upload_url(campaign_id=campaign_id, payload=payload, current_user=current_user)


@router.post("/{campaign_id}/intro-audio/confirm", response_model=CampaignResponse)
async def confirm_intro_audio(
    campaign_id: str,
    payload: IntroAudioConfirmRequest,
    current_user: Dict = Depends(get_current_user_from_token),
):
    return await campaign_service.confirm_intro_audio(campaign_id=campaign_id, payload=payload, current_user=current_user)


@router.post("/{campaign_id}/start", response_model=CampaignControlResponse)
async def start_campaign(campaign_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    return await campaign_service.control_campaign(campaign_id=campaign_id, action="start", current_user=current_user)


@router.post("/{campaign_id}/pause", response_model=CampaignControlResponse)
async def pause_campaign(campaign_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    return await campaign_service.control_campaign(campaign_id=campaign_id, action="pause", current_user=current_user)


@router.post("/{campaign_id}/resume", response_model=CampaignControlResponse)
async def resume_campaign(campaign_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    return await campaign_service.control_campaign(campaign_id=campaign_id, action="resume", current_user=current_user)


@router.post("/{campaign_id}/cancel", response_model=CampaignControlResponse)
async def cancel_campaign(campaign_id: str, current_user: Dict = Depends(get_current_user_from_token)):
    return await campaign_service.control_campaign(campaign_id=campaign_id, action="cancel", current_user=current_user)


@router.get("/{campaign_id}/contacts", response_model=List[CampaignContactResponse])
async def list_contacts(
    campaign_id: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: Dict = Depends(get_current_user_from_token),
):
    rows = await campaign_service.list_contacts(campaign_id=campaign_id, current_user=current_user, limit=limit, offset=offset)
    return [CampaignContactResponse(**row) for row in rows]


@router.get("/{campaign_id}/attempts", response_model=List[CampaignAttemptResponse])
async def list_attempts(
    campaign_id: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: Dict = Depends(get_current_user_from_token),
):
    rows = await campaign_service.list_attempts(campaign_id=campaign_id, current_user=current_user, limit=limit, offset=offset)
    return [CampaignAttemptResponse(**row) for row in rows]

