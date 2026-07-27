"""Twilio integration helpers."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import Dial, VoiceResponse

from app.core.config import settings
from app.core.encryption import encryption_service
from app.services.livekit import build_sip_uri


class TwilioService:
    @staticmethod
    def validate_signature(url: str, params: Dict[str, str], signature: str, auth_token: str) -> bool:
        validator = RequestValidator(auth_token)
        return validator.validate(url, params, signature)

    async def initiate_outbound_call(
        self,
        *,
        tenant_twilio: Dict,
        from_number: str,
        to_number: str,
        campaign_id: str,
        contact_id: str,
        attempt_id: str,
        recording_enabled: bool,
    ) -> str:
        account_sid = tenant_twilio["account_sid"]
        raw_auth_token = tenant_twilio["auth_token"]
        auth_token = self._decrypt_if_needed(raw_auth_token)

        webhook_url = (
            f"{settings.twilio_base_url}/api/v1/cold-caller/twilio/webhook"
            f"?campaign_id={campaign_id}&contact_id={contact_id}&attempt_id={attempt_id}"
        )
        status_url = (
            f"{settings.twilio_base_url}/api/v1/cold-caller/twilio/status"
            f"?campaign_id={campaign_id}&contact_id={contact_id}&attempt_id={attempt_id}"
        )

        def _create_call():
            client = Client(account_sid, auth_token)
            call = client.calls.create(
                from_=from_number,
                to=to_number,
                url=webhook_url,
                status_callback=status_url,
                status_callback_event=["initiated", "ringing", "answered", "completed"],
                machine_detection="Enable",
                record=recording_enabled,
            )
            return call.sid

        return await asyncio.to_thread(_create_call)

    def build_play_then_bridge_twiml(
        self,
        *,
        campaign: Dict,
        call_sid: str,
        to_number: str,
        room_name: str,
        answered_by: Optional[str],
    ) -> VoiceResponse:
        response = VoiceResponse()

        if answered_by and answered_by.lower() in {"machine_start", "machine_end_beep", "machine_end_silence", "fax"}:
            response.hangup()
            return response

        intro = campaign.get("intro_audio") or {}
        intro_url = intro.get("url")
        if intro_url:
            response.play(intro_url)

        sip_uri = build_sip_uri(
            room_name=room_name,
            tenant_id=campaign["tenant_id"],
            call_sid=call_sid,
            called_number=to_number,
        )
        dial = Dial()
        dial.sip(sip_uri)
        response.append(dial)
        return response

    def _decrypt_if_needed(self, token: str) -> str:
        try:
            return encryption_service.decrypt(token)
        except Exception:
            return token


twilio_service = TwilioService()
