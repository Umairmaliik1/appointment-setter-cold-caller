"""Compliance checks for campaign dialing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


@dataclass
class ComplianceResult:
    allowed: bool
    reason: str = ""


class ComplianceService:
    def is_within_call_window(self, campaign: dict, now_utc: datetime | None = None) -> ComplianceResult:
        now_utc = now_utc or datetime.now(timezone.utc)
        timezone_name = campaign.get("compliance", {}).get("timezone", "UTC")
        window_start = campaign.get("compliance", {}).get("call_window_start", "09:00")
        window_end = campaign.get("compliance", {}).get("call_window_end", "18:00")

        try:
            if timezone_name.upper() == "UTC":
                local_now = now_utc.astimezone(timezone.utc)
            else:
                local_now = now_utc.astimezone(ZoneInfo(timezone_name))
        except Exception:
            return ComplianceResult(False, f"Invalid timezone: {timezone_name}")

        current = local_now.strftime("%H:%M")
        if current < window_start or current > window_end:
            return ComplianceResult(
                False, f"Outside campaign calling window ({window_start}-{window_end} {timezone_name})"
            )

        return ComplianceResult(True)

    def can_retry(self, campaign: dict, contact: dict, call_outcome: str) -> bool:
        compliance = campaign.get("compliance", {})
        retry_on = set(compliance.get("retry_on_statuses", ["busy", "no-answer"]))
        max_attempts = int(compliance.get("max_attempts_per_contact", 3))
        if call_outcome not in retry_on:
            return False
        return int(contact.get("attempt_count", 0)) < max_attempts


compliance_service = ComplianceService()
