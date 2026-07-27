"""Sequential campaign dialer service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Optional

from app.core.config import settings
from app.core.time import utcnow_iso
from app.repositories.campaign_repository import campaign_repository
from app.services.compliance import compliance_service
from app.services.firebase import firebase_service
from app.services.redis_client import async_redis_client
from app.services.twilio_service import twilio_service


TERMINAL_TWILIO_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled"}
MACHINE_ANSWERED = {"machine_start", "machine_end_beep", "machine_end_silence", "fax"}


class DialerService:
    async def kick_campaign(self, campaign_id: str, triggered_by: str, reason: str) -> None:
        lease_owner = f"dialer:{triggered_by}:{uuid.uuid4().hex[:8]}"
        leased = await campaign_repository.acquire_campaign_lease(
            campaign_id=campaign_id,
            lease_owner=lease_owner,
            lease_seconds=settings.CAMPAIGN_LEASE_SECONDS,
        )
        if not leased:
            return

        try:
            campaign = await campaign_repository.get_campaign(campaign_id)
            if not campaign or campaign.get("status") != "running":
                return
            if campaign.get("active_call_sid"):
                return

            now = datetime.now(timezone.utc)
            window = compliance_service.is_within_call_window(campaign, now_utc=now)
            if not window.allowed:
                await self._event(campaign, "campaign.waiting_window", window.reason, {"reason": reason})
                return

            contact = await campaign_repository.get_next_contact_for_dial(campaign_id=campaign_id, now_iso=now.isoformat())
            if not contact:
                await self._finalize_if_done(campaign)
                return

            attempts_today = await campaign_repository.count_attempts_for_contact_since(
                contact_id=contact["id"], since_iso=self._local_day_start_utc_iso(campaign, now)
            )
            max_per_day = int(campaign.get("compliance", {}).get("max_attempts_per_day", 1))
            if attempts_today >= max_per_day:
                retry_at = self._next_local_day_window_start_utc_iso(campaign, now)
                await campaign_repository.update_contact(
                    contact["id"],
                    {
                        "status": "retry_scheduled",
                        "next_attempt_at": retry_at,
                        "updated_at": utcnow_iso(),
                        "last_outcome": "daily_cap_reached",
                    },
                )
                await self._event(campaign, "contact.daily_cap", "Daily attempt cap reached", {"contact_id": contact["id"]})
                return

            attempt_number = int(contact.get("attempt_count", 0)) + 1
            attempt_id = str(uuid.uuid4())
            room_name = f"cold-{campaign_id[:8]}-{contact['id'][:8]}-{attempt_number}"
            attempt = {
                "id": attempt_id,
                "campaign_id": campaign_id,
                "contact_id": contact["id"],
                "tenant_id": campaign["tenant_id"],
                "twilio_call_sid": None,
                "attempt_number": attempt_number,
                "status": "initiated",
                "answered_by": None,
                "error_code": None,
                "error_message": None,
                "duration_seconds": None,
                "room_name": room_name,
                "created_at": utcnow_iso(),
                "updated_at": utcnow_iso(),
                "completed_at": None,
            }
            await campaign_repository.create_attempt(attempt)

            twilio_integration = await firebase_service.get_twilio_integration(campaign["tenant_id"])
            if not twilio_integration:
                raise ValueError("Twilio integration missing for tenant")
            outbound_phone = await self._resolve_campaign_outbound_phone(campaign)

            call_sid = await twilio_service.initiate_outbound_call(
                tenant_twilio=twilio_integration,
                from_number=outbound_phone["phone_number"],
                to_number=contact["phone_number"],
                campaign_id=campaign_id,
                contact_id=contact["id"],
                attempt_id=attempt_id,
                recording_enabled=bool(campaign.get("recording_enabled", False)),
            )

            await campaign_repository.update_attempt(
                attempt_id,
                {
                    "twilio_call_sid": call_sid,
                    "status": "calling",
                    "updated_at": utcnow_iso(),
                },
            )

            await campaign_repository.update_contact(
                contact["id"],
                {
                    "status": "calling",
                    "attempt_count": attempt_number,
                    "last_attempt_at": utcnow_iso(),
                    "next_attempt_at": None,
                    "updated_at": utcnow_iso(),
                    "twilio_call_sid": call_sid,
                },
            )

            await campaign_repository.update_campaign(
                campaign_id,
                {
                    "active_contact_id": contact["id"],
                    "active_call_sid": call_sid,
                    "active_attempt_id": attempt_id,
                    "in_progress_contacts": 1,
                    "updated_at": utcnow_iso(),
                    "last_error": None,
                },
            )

            await self._store_worker_call_config(campaign=campaign, call_sid=call_sid, contact=contact, attempt_id=attempt_id)
            await self._event(
                campaign,
                "dialer.call_initiated",
                f"Initiated call to {contact['phone_number']}",
                {"contact_id": contact["id"], "attempt_id": attempt_id, "call_sid": call_sid},
            )
        except Exception as exc:
            await campaign_repository.update_campaign(campaign_id, {"last_error": str(exc), "updated_at": utcnow_iso()})
            campaign = await campaign_repository.get_campaign(campaign_id)
            if campaign:
                await self._event(campaign, "dialer.error", "Dialer failed to initiate call", {"error": str(exc)})
        finally:
            await campaign_repository.release_campaign_lease(campaign_id, lease_owner=lease_owner)

    async def handle_status_callback(
        self,
        *,
        call_sid: str,
        call_status: str,
        answered_by: Optional[str],
        call_duration: Optional[str],
        error_code: Optional[str],
        error_message: Optional[str],
    ) -> None:
        attempt = await campaign_repository.get_attempt_by_call_sid(call_sid)
        if not attempt:
            return

        campaign = await campaign_repository.get_campaign(attempt["campaign_id"])
        contact = await campaign_repository.get_contact(attempt["contact_id"])
        if not campaign or not contact:
            return

        call_status = (call_status or "").strip().lower()
        answered_by_norm = (answered_by or "").strip().lower() or None
        now = utcnow_iso()
        terminal = call_status in TERMINAL_TWILIO_STATUSES

        if not terminal:
            await campaign_repository.update_attempt(
                attempt["id"],
                {
                    "status": call_status or attempt.get("status", "unknown"),
                    "answered_by": answered_by_norm,
                    "updated_at": now,
                },
            )
            return

        prior_status = (attempt.get("status") or "").lower()
        if prior_status in {"completed", "busy", "failed", "no-answer", "canceled", "machine"}:
            return

        final_status = call_status
        if answered_by_norm in MACHINE_ANSWERED:
            final_status = "machine"

        await campaign_repository.update_attempt(
            attempt["id"],
            {
                "status": final_status,
                "answered_by": answered_by_norm,
                "duration_seconds": int(call_duration) if call_duration and call_duration.isdigit() else None,
                "error_code": error_code,
                "error_message": error_message,
                "completed_at": now,
                "updated_at": now,
            },
        )

        campaign_updates = {
            "active_contact_id": None,
            "active_call_sid": None,
            "active_attempt_id": None,
            "in_progress_contacts": 0,
            "updated_at": now,
        }
        await campaign_repository.update_campaign(campaign["id"], campaign_updates)
        await async_redis_client.delete(f"call_config:{call_sid}")

        if final_status == "completed":
            await campaign_repository.update_contact(
                contact["id"],
                {
                    "status": "completed",
                    "last_outcome": "completed",
                    "updated_at": now,
                },
            )
        elif final_status == "machine":
            await campaign_repository.update_contact(
                contact["id"],
                {
                    "status": "failed",
                    "last_outcome": "machine_detected",
                    "updated_at": now,
                },
            )
        else:
            if compliance_service.can_retry(campaign, contact, final_status):
                retry_at = (datetime.now(timezone.utc) + timedelta(minutes=int(campaign["compliance"]["retry_delay_minutes"]))).isoformat()
                await campaign_repository.update_contact(
                    contact["id"],
                    {
                        "status": "retry_scheduled",
                        "next_attempt_at": retry_at,
                        "last_outcome": final_status,
                        "updated_at": now,
                    },
                )
            else:
                await campaign_repository.update_contact(
                    contact["id"],
                    {
                        "status": "failed",
                        "last_outcome": final_status,
                        "updated_at": now,
                    },
                )

        await self.sync_campaign_counters(campaign["id"])
        campaign_after = await campaign_repository.get_campaign(campaign["id"])
        if campaign_after and campaign_after.get("status") == "running":
            await self.kick_campaign(campaign_id=campaign["id"], triggered_by="status-callback", reason="status_update")

    async def sync_campaign_counters(self, campaign_id: str) -> None:
        completed = await campaign_repository.count_contacts_by_status(campaign_id, ["completed"])
        failed = await campaign_repository.count_contacts_by_status(campaign_id, ["failed"])
        dnc = await campaign_repository.count_contacts_by_status(campaign_id, ["dnc_skipped"])
        in_progress = await campaign_repository.count_contacts_by_status(campaign_id, ["calling"])

        updates = {
            "completed_contacts": completed,
            "failed_contacts": failed,
            "dnc_contacts": dnc,
            "in_progress_contacts": in_progress,
            "updated_at": utcnow_iso(),
        }
        await campaign_repository.update_campaign(campaign_id, updates)

    async def _finalize_if_done(self, campaign: Dict) -> None:
        pending = await campaign_repository.count_contacts_by_status(campaign["id"], ["pending", "retry_scheduled", "calling"])
        if pending > 0:
            return
        await self.sync_campaign_counters(campaign["id"])
        await campaign_repository.update_campaign(
            campaign["id"],
            {
                "status": "completed",
                "completed_at": utcnow_iso(),
                "updated_at": utcnow_iso(),
                "active_contact_id": None,
                "active_call_sid": None,
                "active_attempt_id": None,
            },
        )
        done = await campaign_repository.get_campaign(campaign["id"])
        if done:
            await self._event(done, "campaign.completed", "Campaign completed", {})

    async def _store_worker_call_config(self, campaign: Dict, call_sid: str, contact: Dict, attempt_id: str) -> None:
        agent = await firebase_service.get_agent(campaign["voice_agent_id"])
        if not agent:
            raise ValueError("Configured voice agent not found")

        config = {
            "agent_id": campaign["voice_agent_id"],
            "tenant_id": campaign["tenant_id"],
            "call_id": attempt_id,
            "campaign_id": campaign["id"],
            "contact_id": contact["id"],
            "service_type": agent.get("service_type") or "Cold Calling",
            "voice_id": agent.get("voice_id"),
            "agent_type": "voice",
            "agent_data": {
                "id": agent.get("id"),
                "agent_type": "voice",
                "name": agent.get("name"),
                "voice_id": agent.get("voice_id"),
                "language": agent.get("language"),
                "greeting_message": agent.get("greeting_message"),
                "service_type": agent.get("service_type"),
                "tenant_id": agent.get("tenant_id"),
            },
            "call_type": "outbound_cold",
            "customer_name": contact.get("name"),
            "customer_phone": contact["phone_number"],
            "customer_notes": contact.get("notes"),
            "outbound_phone_number": (campaign.get("outbound_phone_number") or {}).get("phone_number"),
            "recording_enabled": bool(campaign.get("recording_enabled", False)),
            "created_at": utcnow_iso(),
        }
        await async_redis_client.set_json(f"call_config:{call_sid}", config, ttl=settings.CALL_CONFIG_TTL_SECONDS)

    async def _resolve_campaign_outbound_phone(self, campaign: Dict) -> Dict:
        outbound_phone_id = campaign.get("outbound_phone_number_id")
        if not outbound_phone_id:
            raise ValueError("Campaign outbound_phone_number_id is missing")

        phone = await firebase_service.get_phone_number(outbound_phone_id)
        if not phone:
            raise ValueError("Campaign outbound phone number no longer exists")
        if phone.get("tenant_id") != campaign["tenant_id"]:
            raise ValueError("Campaign outbound phone number is outside tenant scope")

        usage_role = phone.get("usage_role") or "voice_agent_inbound"
        role_status = phone.get("role_status")
        if not role_status:
            role_status = "active" if phone.get("status", "active") == "active" else "inactive"

        if usage_role != "cold_caller_outbound":
            raise ValueError("Campaign outbound phone number is not bound to cold-caller outbound role")
        if role_status != "active" or phone.get("status", "active") != "active":
            raise ValueError("Campaign outbound phone number is inactive")
        if phone.get("conflict_code"):
            raise ValueError(phone.get("conflict_message") or "Campaign outbound phone number is in conflict")
        if not phone.get("phone_number"):
            raise ValueError("Campaign outbound phone number value is missing")

        return phone

    async def _event(self, campaign: Dict, event_type: str, message: str, metadata: Dict) -> None:
        await campaign_repository.create_runtime_event(
            {
                "id": str(uuid.uuid4()),
                "campaign_id": campaign["id"],
                "tenant_id": campaign["tenant_id"],
                "event_type": event_type,
                "message": message,
                "metadata": metadata,
                "created_at": utcnow_iso(),
            }
        )

    def _local_day_start_utc_iso(self, campaign: Dict, now_utc: datetime) -> str:
        tz_name = campaign.get("compliance", {}).get("timezone", "UTC")
        local = now_utc.astimezone(ZoneInfo(tz_name))
        local_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return local_start.astimezone(timezone.utc).isoformat()

    def _next_local_day_window_start_utc_iso(self, campaign: Dict, now_utc: datetime) -> str:
        tz_name = campaign.get("compliance", {}).get("timezone", "UTC")
        start_hhmm = campaign.get("compliance", {}).get("call_window_start", "09:00")
        start_hour, start_minute = [int(x) for x in start_hhmm.split(":")]
        local = now_utc.astimezone(ZoneInfo(tz_name))
        next_day = (local + timedelta(days=1)).replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        return next_day.astimezone(timezone.utc).isoformat()


dialer_service = DialerService()
