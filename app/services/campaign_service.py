"""Campaign application service."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException, UploadFile, status

from app.api.v1.schemas.campaign import (
    CampaignControlResponse,
    CampaignCreateRequest,
    CampaignResponse,
    CampaignUpdateRequest,
    ContactUploadRejectedItem,
    ContactUploadResponse,
    IntroAudioConfirmRequest,
    IntroAudioUploadUrlRequest,
    IntroAudioUploadUrlResponse,
)
from app.core.config import settings
from app.core.phone import normalize_phone_number
from app.core.time import utcnow_iso
from app.repositories.campaign_repository import campaign_repository
from app.services.firebase import firebase_service
from app.services.storage import storage_service


class CampaignService:
    async def create_campaign(self, payload: CampaignCreateRequest, current_user: Dict) -> CampaignResponse:
        await self._assert_voice_agent_access(payload.tenant_id, payload.voice_agent_id, current_user)
        outbound_phone = await self._assert_outbound_phone_access(
            payload.tenant_id, payload.outbound_phone_number_id, current_user
        )
        await self._assert_twilio_configured(payload.tenant_id)

        now = utcnow_iso()
        campaign = {
            "id": str(uuid.uuid4()),
            "tenant_id": payload.tenant_id,
            "name": payload.name.strip(),
            "description": payload.description.strip(),
            "voice_agent_id": payload.voice_agent_id,
            "outbound_phone_number_id": outbound_phone["id"],
            "outbound_phone_number": self._to_outbound_phone_metadata(outbound_phone),
            "status": "draft",
            "recording_enabled": payload.recording_enabled,
            "recording_disclosure": payload.recording_disclosure.strip(),
            "compliance": payload.compliance.model_dump(),
            "intro_audio": None,
            "total_contacts": 0,
            "completed_contacts": 0,
            "failed_contacts": 0,
            "dnc_contacts": 0,
            "in_progress_contacts": 0,
            "created_by": str(current_user.get("id")),
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "active_contact_id": None,
            "active_call_sid": None,
            "active_attempt_id": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error": None,
        }
        await campaign_repository.create_campaign(campaign)
        await self._event(campaign, "campaign.created", f"Campaign '{campaign['name']}' created", current_user)
        return self._to_campaign_response(campaign)

    async def list_campaigns(self, tenant_id: str, current_user: Dict, limit: int, offset: int) -> List[CampaignResponse]:
        self._verify_tenant_access(current_user, tenant_id)
        rows = await campaign_repository.list_campaigns(tenant_id=tenant_id, limit=limit, offset=offset)
        return [self._to_campaign_response(row) for row in rows]

    async def get_campaign(self, campaign_id: str, current_user: Dict) -> CampaignResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])
        return self._to_campaign_response(campaign)

    async def update_campaign(self, campaign_id: str, payload: CampaignUpdateRequest, current_user: Dict) -> CampaignResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])
        if campaign["status"] not in {"draft", "paused", "ready"}:
            raise HTTPException(status_code=409, detail="Campaign can only be edited in draft/paused/ready state")

        updates = payload.model_dump(exclude_none=True)
        if "name" in updates:
            updates["name"] = updates["name"].strip()
        if "description" in updates:
            updates["description"] = updates["description"].strip()
        if "recording_disclosure" in updates and updates["recording_disclosure"] is not None:
            updates["recording_disclosure"] = updates["recording_disclosure"].strip()

        if "voice_agent_id" in updates:
            await self._assert_voice_agent_access(campaign["tenant_id"], updates["voice_agent_id"], current_user)
        if "outbound_phone_number_id" in updates:
            outbound_phone = await self._assert_outbound_phone_access(
                campaign["tenant_id"], updates["outbound_phone_number_id"], current_user
            )
            updates["outbound_phone_number"] = self._to_outbound_phone_metadata(outbound_phone)

        updates["updated_at"] = utcnow_iso()
        saved = await campaign_repository.update_campaign(campaign_id, updates)
        assert saved is not None
        await self._event(saved, "campaign.updated", "Campaign updated", current_user)
        return self._to_campaign_response(saved)

    async def upload_contacts(
        self,
        campaign_id: str,
        file: UploadFile,
        current_user: Dict,
    ) -> ContactUploadResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])
        if campaign["status"] not in {"draft", "ready", "paused"}:
            raise HTTPException(status_code=409, detail="Contacts can only be uploaded in draft/ready/paused state")
        if not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV uploads are supported")

        content = (await file.read()).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or "phone_number" not in [name.strip() for name in reader.fieldnames]:
            raise HTTPException(status_code=400, detail="CSV must include 'phone_number' column")

        dnc_set = await campaign_repository.get_dnc_phone_set(campaign["tenant_id"])
        excluded_numbers = set((campaign.get("compliance", {}).get("excluded_numbers") or []))
        seen = set()
        accepted: List[Dict] = []
        rejected: List[ContactUploadRejectedItem] = []
        now = utcnow_iso()

        for idx, row in enumerate(reader, start=2):
            raw_phone = (row.get("phone_number") or "").strip()
            raw_name = (row.get("name") or "").strip()
            raw_notes = (row.get("notes") or "").strip()

            try:
                normalized = normalize_phone_number(raw_phone)
            except ValueError:
                rejected.append(ContactUploadRejectedItem(row_number=idx, phone_number=raw_phone or None, reason="Invalid phone format"))
                continue

            if normalized in seen:
                rejected.append(ContactUploadRejectedItem(row_number=idx, phone_number=normalized, reason="Duplicate number in file"))
                continue
            seen.add(normalized)

            existing = await campaign_repository.get_contact_by_phone(campaign_id, normalized)
            if existing:
                rejected.append(
                    ContactUploadRejectedItem(row_number=idx, phone_number=normalized, reason="Number already exists in campaign")
                )
                continue

            if normalized in dnc_set or normalized in excluded_numbers:
                rejected.append(ContactUploadRejectedItem(row_number=idx, phone_number=normalized, reason="Suppressed by DNC/exclusions"))
                continue

            accepted.append(
                {
                    "id": str(uuid.uuid4()),
                    "campaign_id": campaign_id,
                    "tenant_id": campaign["tenant_id"],
                    "phone_number": normalized,
                    "name": raw_name or None,
                    "notes": raw_notes or None,
                    "status": "pending",
                    "attempt_count": 0,
                    "next_attempt_at": now,
                    "last_attempt_at": None,
                    "last_outcome": None,
                    "twilio_call_sid": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        await campaign_repository.create_contacts_bulk(accepted)

        total = int(campaign.get("total_contacts", 0)) + len(accepted)
        status_value = "ready" if total > 0 else campaign["status"]
        updated = await campaign_repository.update_campaign(
            campaign_id,
            {
                "total_contacts": total,
                "status": status_value,
                "updated_at": now,
            },
        )
        if updated:
            await self._event(updated, "campaign.contacts_uploaded", f"{len(accepted)} contacts uploaded", current_user)

        return ContactUploadResponse(
            campaign_id=campaign_id,
            accepted_count=len(accepted),
            rejected_count=len(rejected),
            total_rows=max(0, len(accepted) + len(rejected)),
            rejected=rejected[:200],
        )

    async def create_intro_audio_upload_url(
        self, campaign_id: str, payload: IntroAudioUploadUrlRequest, current_user: Dict
    ) -> IntroAudioUploadUrlResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])
        if campaign["status"] not in {"draft", "ready", "paused"}:
            raise HTTPException(status_code=409, detail="Intro audio can only be updated in draft/ready/paused")

        if payload.content_type not in {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"}:
            raise HTTPException(status_code=400, detail="Unsupported audio content type")

        try:
            generated = storage_service.generate_upload_url(
                tenant_id=campaign["tenant_id"],
                campaign_id=campaign_id,
                file_name=payload.file_name,
                content_type=payload.content_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return IntroAudioUploadUrlResponse(
            campaign_id=campaign_id,
            upload_url=generated["upload_url"],
            object_key=generated["object_key"],
            public_url=generated["public_url"],
            expires_in_seconds=settings.PRESIGNED_URL_EXPIRES_SECONDS,
        )

    async def confirm_intro_audio(self, campaign_id: str, payload: IntroAudioConfirmRequest, current_user: Dict) -> CampaignResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])

        if not storage_service.confirm_object_exists(payload.object_key):
            raise HTTPException(status_code=400, detail="Uploaded intro audio object not found")

        intro = {
            "object_key": payload.object_key,
            "url": payload.public_url or settings.s3_public_url(payload.object_key),
            "content_type": payload.content_type,
            "file_name": payload.file_name,
            "confirmed": True,
            "uploaded_at": utcnow_iso(),
        }
        saved = await campaign_repository.update_campaign(campaign_id, {"intro_audio": intro, "updated_at": utcnow_iso()})
        assert saved is not None
        await self._event(saved, "campaign.intro_audio_confirmed", "Intro audio confirmed", current_user)
        return self._to_campaign_response(saved)

    async def control_campaign(self, campaign_id: str, action: str, current_user: Dict) -> CampaignControlResponse:
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])

        updates = {"updated_at": utcnow_iso()}
        message = ""

        if action == "start":
            if campaign["status"] not in {"ready", "paused", "draft"}:
                raise HTTPException(status_code=409, detail="Campaign cannot be started from current state")
            if not campaign.get("intro_audio", {}).get("confirmed"):
                raise HTTPException(status_code=409, detail="Intro audio must be uploaded and confirmed before start")
            if int(campaign.get("total_contacts", 0)) <= 0:
                raise HTTPException(status_code=409, detail="Campaign has no contacts")
            outbound_phone = await self._assert_outbound_phone_access(
                campaign["tenant_id"], campaign.get("outbound_phone_number_id"), current_user
            )
            updates["status"] = "running"
            updates["started_at"] = campaign.get("started_at") or utcnow_iso()
            updates["outbound_phone_number"] = self._to_outbound_phone_metadata(outbound_phone)
            message = "Campaign started"
        elif action == "pause":
            if campaign["status"] != "running":
                raise HTTPException(status_code=409, detail="Only running campaigns can be paused")
            updates["status"] = "paused"
            message = "Campaign paused"
        elif action == "resume":
            if campaign["status"] != "paused":
                raise HTTPException(status_code=409, detail="Only paused campaigns can be resumed")
            outbound_phone = await self._assert_outbound_phone_access(
                campaign["tenant_id"], campaign.get("outbound_phone_number_id"), current_user
            )
            updates["status"] = "running"
            updates["outbound_phone_number"] = self._to_outbound_phone_metadata(outbound_phone)
            message = "Campaign resumed"
        elif action == "cancel":
            if campaign["status"] in {"completed", "canceled"}:
                raise HTTPException(status_code=409, detail="Campaign already finished")
            updates["status"] = "canceled"
            updates["completed_at"] = utcnow_iso()
            message = "Campaign canceled"
        else:
            raise HTTPException(status_code=400, detail="Invalid campaign action")

        saved = await campaign_repository.update_campaign(campaign_id, updates)
        assert saved is not None
        await self._event(saved, f"campaign.{action}", message, current_user)

        if saved["status"] == "running":
            from app.services.dialer_service import dialer_service

            await dialer_service.kick_campaign(campaign_id=saved["id"], triggered_by=str(current_user.get("id")), reason=action)

        return CampaignControlResponse(campaign_id=saved["id"], status=saved["status"], message=message)

    async def list_contacts(self, campaign_id: str, current_user: Dict, limit: int, offset: int):
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])
        return await campaign_repository.list_contacts(campaign_id=campaign_id, limit=limit, offset=offset)

    async def list_attempts(self, campaign_id: str, current_user: Dict, limit: int, offset: int):
        campaign = await self._get_campaign_or_404(campaign_id)
        self._verify_tenant_access(current_user, campaign["tenant_id"])
        return await campaign_repository.list_attempts(campaign_id=campaign_id, limit=limit, offset=offset)

    async def _assert_voice_agent_access(self, tenant_id: str, voice_agent_id: str, current_user: Dict) -> None:
        self._verify_tenant_access(current_user, tenant_id)
        agent = await firebase_service.get_agent(voice_agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Voice agent not found")
        if agent.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Voice agent not in tenant scope")
        if (agent.get("agent_type") or "voice") != "voice":
            raise HTTPException(status_code=400, detail="Selected agent must be a voice agent")

    async def _assert_twilio_configured(self, tenant_id: str) -> None:
        twilio = await firebase_service.get_twilio_integration(tenant_id)
        if not twilio:
            raise HTTPException(status_code=409, detail="Twilio integration is required for this tenant")

    async def _assert_outbound_phone_access(
        self, tenant_id: str, outbound_phone_number_id: Optional[str], current_user: Dict
    ) -> Dict:
        self._verify_tenant_access(current_user, tenant_id)
        if not outbound_phone_number_id:
            raise HTTPException(status_code=409, detail="Campaign requires outbound_phone_number_id")

        phone = await firebase_service.get_phone_number(outbound_phone_number_id)
        if not phone:
            raise HTTPException(status_code=404, detail="Outbound phone number not found")
        if phone.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Outbound phone number not in tenant scope")

        usage_role = phone.get("usage_role") or "voice_agent_inbound"
        role_status = phone.get("role_status")
        if not role_status:
            role_status = "active" if phone.get("status", "active") == "active" else "inactive"
        conflict_code = phone.get("conflict_code")
        conflict_message = phone.get("conflict_message")

        if usage_role != "cold_caller_outbound":
            raise HTTPException(status_code=409, detail="Selected outbound number is not bound to Cold Caller outbound role")
        if role_status != "active" or phone.get("status", "active") != "active":
            raise HTTPException(status_code=409, detail="Selected outbound number is not active")
        if conflict_code:
            raise HTTPException(status_code=409, detail=conflict_message or "Selected outbound number is in conflict state")

        return {
            **phone,
            "usage_role": usage_role,
            "role_status": role_status,
        }

    async def _get_campaign_or_404(self, campaign_id: str) -> Dict:
        campaign = await campaign_repository.get_campaign(campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return campaign

    def _verify_tenant_access(self, current_user: Dict, tenant_id: str) -> None:
        role = current_user.get("role", "user")
        if role == "admin":
            return
        if current_user.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied for tenant")

    async def _event(self, campaign: Dict, event_type: str, message: str, user: Dict) -> None:
        await campaign_repository.create_runtime_event(
            {
                "id": str(uuid.uuid4()),
                "campaign_id": campaign["id"],
                "tenant_id": campaign["tenant_id"],
                "event_type": event_type,
                "message": message,
                "metadata": {"user_id": str(user.get("id"))},
                "created_at": utcnow_iso(),
            }
        )

    def _to_outbound_phone_metadata(self, phone: Dict) -> Dict:
        return {
            "id": phone.get("id"),
            "phone_number": phone.get("phone_number"),
            "usage_role": phone.get("usage_role") or "voice_agent_inbound",
            "role_status": phone.get("role_status") or "active",
        }

    def _to_campaign_response(self, campaign: Dict) -> CampaignResponse:
        normalized = dict(campaign)
        normalized.setdefault("outbound_phone_number_id", None)
        normalized.setdefault("outbound_phone_number", None)
        return CampaignResponse(**normalized)


campaign_service = CampaignService()
