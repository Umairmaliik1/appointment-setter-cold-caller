"""DNC management service."""

from __future__ import annotations

import csv
import hashlib
import io
from typing import Dict, List

from fastapi import HTTPException, UploadFile

from app.api.v1.schemas.dnc import DncUploadResponse
from app.core.phone import normalize_phone_number
from app.core.time import utcnow_iso
from app.repositories.campaign_repository import campaign_repository


class DncService:
    async def upload_dnc_csv(self, tenant_id: str, file: UploadFile, current_user: Dict) -> DncUploadResponse:
        self._verify_tenant_access(current_user, tenant_id)
        if not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV uploads are supported for DNC")

        content = (await file.read()).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or "phone_number" not in [name.strip() for name in reader.fieldnames]:
            raise HTTPException(status_code=400, detail="CSV must include 'phone_number' column")

        existing = await campaign_repository.get_dnc_phone_set(tenant_id)
        accepted: List[Dict] = []
        ignored: List[str] = []
        seen = set()
        now = utcnow_iso()
        actor = str(current_user.get("id"))

        for row in reader:
            raw_phone = (row.get("phone_number") or "").strip()
            if not raw_phone:
                continue
            try:
                phone = normalize_phone_number(raw_phone)
            except ValueError:
                ignored.append(raw_phone)
                continue

            if phone in existing or phone in seen:
                ignored.append(phone)
                continue

            seen.add(phone)
            digest = hashlib.sha1(f"{tenant_id}:{phone}".encode()).hexdigest()
            accepted.append(
                {
                    "id": digest,
                    "tenant_id": tenant_id,
                    "phone_number": phone,
                    "source": "upload",
                    "created_by": actor,
                    "created_at": now,
                }
            )

        await campaign_repository.create_dnc_entries_bulk(accepted)

        return DncUploadResponse(
            tenant_id=tenant_id,
            accepted_count=len(accepted),
            ignored_count=len(ignored),
            total_rows=len(accepted) + len(ignored),
            ignored_numbers=ignored[:200],
        )

    def _verify_tenant_access(self, current_user: Dict, tenant_id: str) -> None:
        role = current_user.get("role", "user")
        if role == "admin":
            return
        if current_user.get("tenant_id") != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied for tenant")


dnc_service = DncService()

