"""Twilio webhook endpoints for cold caller."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.core.phone import normalize_phone_number_safe
from app.repositories.campaign_repository import campaign_repository
from app.services.dialer_service import dialer_service
from app.services.firebase import firebase_service
from app.services.twilio_service import twilio_service

router = APIRouter(prefix="/cold-caller/twilio", tags=["cold-caller-twilio"])


async def _validate_twilio_signature(request: Request, campaign_id: str, form_data: dict) -> bool:
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        return False

    campaign = await campaign_repository.get_campaign(campaign_id)
    if not campaign:
        return False
    twilio_integration = await firebase_service.get_twilio_integration(campaign["tenant_id"])
    if not twilio_integration:
        return False

    auth_token = twilio_service._decrypt_if_needed(twilio_integration.get("auth_token", ""))
    url = str(request.url)
    params = {k: str(v) for k, v in form_data.items()}
    return twilio_service.validate_signature(url=url, params=params, signature=signature, auth_token=auth_token)


@router.post("/webhook")
async def twilio_webhook(
    request: Request,
    campaign_id: str = Query(...),
    contact_id: Optional[str] = Query(None),
    attempt_id: Optional[str] = Query(None),
):
    form = await request.form()
    form_dict = dict(form)

    if not await _validate_twilio_signature(request, campaign_id, form_dict):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    campaign = await campaign_repository.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    call_sid = form_dict.get("CallSid")
    to_number = normalize_phone_number_safe(form_dict.get("To")) or (form_dict.get("To") or "")
    answered_by = form_dict.get("AnsweredBy")

    attempt = await campaign_repository.get_attempt(attempt_id) if attempt_id else None
    if not attempt and call_sid:
        attempt = await campaign_repository.get_attempt_by_call_sid(call_sid)
    if attempt and call_sid and not attempt.get("twilio_call_sid"):
        await campaign_repository.update_attempt(attempt["id"], {"twilio_call_sid": call_sid, "updated_at": form_dict.get("Timestamp")})

    room_name = (attempt or {}).get("room_name") or f"cold-{campaign_id[:8]}-{(contact_id or 'contact')[:8]}"
    twiml = twilio_service.build_play_then_bridge_twiml(
        campaign=campaign,
        call_sid=call_sid,
        to_number=to_number,
        room_name=room_name,
        answered_by=answered_by,
    )
    return Response(content=str(twiml), media_type="application/xml")


@router.post("/status")
async def twilio_status_callback(
    request: Request,
    campaign_id: str = Query(...),
    contact_id: Optional[str] = Query(None),
    attempt_id: Optional[str] = Query(None),
):
    form = await request.form()
    form_dict = dict(form)

    if not await _validate_twilio_signature(request, campaign_id, form_dict):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    call_sid = form_dict.get("CallSid")
    call_status = form_dict.get("CallStatus") or ""
    answered_by = form_dict.get("AnsweredBy")
    call_duration = form_dict.get("CallDuration")
    error_code = form_dict.get("ErrorCode") or form_dict.get("SipResponseCode")
    error_message = form_dict.get("ErrorMessage")

    await dialer_service.handle_status_callback(
        call_sid=call_sid,
        call_status=call_status,
        answered_by=answered_by,
        call_duration=call_duration,
        error_code=error_code,
        error_message=error_message,
    )
    return Response(status_code=200)

