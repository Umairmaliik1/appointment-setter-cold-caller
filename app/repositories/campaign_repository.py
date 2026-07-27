"""Cold caller repository layer."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud import firestore

from app.services.firebase import firebase_service

COLD_CAMPAIGNS = "cold_campaigns"
COLD_CONTACTS = "cold_campaign_contacts"
COLD_ATTEMPTS = "cold_call_attempts"
COLD_DNC = "cold_dnc_entries"
COLD_EVENTS = "cold_runtime_events"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class CampaignRepository:
    def __init__(self) -> None:
        self.db = firebase_service.db
        self._run = firebase_service._run

    def _require_db(self) -> None:
        if self.db is None:
            raise RuntimeError("Firebase is not configured")

    async def create_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await firebase_service.create_document(COLD_CAMPAIGNS, payload["id"], payload)

    async def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        return await firebase_service.get_document(COLD_CAMPAIGNS, campaign_id)

    async def list_campaigns(self, tenant_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        filters = [FieldFilter("tenant_id", "==", tenant_id)]
        return await firebase_service.list_documents(COLD_CAMPAIGNS, filters=filters, order_by="created_at", limit=limit, offset=offset)

    async def list_running_campaigns(self, limit: int = 1000) -> List[Dict[str, Any]]:
        filters = [FieldFilter("status", "==", "running")]
        return await firebase_service.list_documents(COLD_CAMPAIGNS, filters=filters, order_by="updated_at", limit=limit, offset=0)

    async def update_campaign(self, campaign_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await firebase_service.update_document(COLD_CAMPAIGNS, campaign_id, updates)

    async def acquire_campaign_lease(self, campaign_id: str, lease_owner: str, lease_seconds: int) -> Optional[Dict[str, Any]]:
        def _acquire():
            self._require_db()
            campaign_ref = self.db.collection(COLD_CAMPAIGNS).document(campaign_id)
            transaction = self.db.transaction()

            @firestore.transactional
            def _txn(txn):
                snapshot = campaign_ref.get(transaction=txn)
                if not snapshot.exists:
                    return None
                data = snapshot.to_dict()
                now = _utc_now()
                expires_at = _parse_iso(data.get("lease_expires_at"))
                current_owner = data.get("lease_owner")

                if expires_at and expires_at > now and current_owner and current_owner != lease_owner:
                    return None

                updates = {
                    "lease_owner": lease_owner,
                    "lease_expires_at": (now + timedelta(seconds=lease_seconds)).isoformat(),
                    "updated_at": now.isoformat(),
                }
                txn.update(campaign_ref, updates)
                data.update(updates)
                return data

            return _txn(transaction)

        return await self._run(_acquire)

    async def release_campaign_lease(self, campaign_id: str, lease_owner: str) -> None:
        def _release():
            self._require_db()
            campaign_ref = self.db.collection(COLD_CAMPAIGNS).document(campaign_id)
            snapshot = campaign_ref.get()
            if not snapshot.exists:
                return
            data = snapshot.to_dict()
            if data.get("lease_owner") == lease_owner:
                campaign_ref.update({"lease_owner": None, "lease_expires_at": None, "updated_at": _utc_now().isoformat()})

        await self._run(_release)

    async def create_contacts_bulk(self, contacts: List[Dict[str, Any]]) -> None:
        if not contacts:
            return

        def _write():
            self._require_db()
            batch = self.db.batch()
            for contact in contacts:
                ref = self.db.collection(COLD_CONTACTS).document(contact["id"])
                batch.set(ref, contact)
            batch.commit()

        await self._run(_write)

    async def list_contacts(self, campaign_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        filters = [FieldFilter("campaign_id", "==", campaign_id)]
        return await firebase_service.list_documents(COLD_CONTACTS, filters=filters, order_by="created_at", limit=limit, offset=offset)

    async def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        return await firebase_service.get_document(COLD_CONTACTS, contact_id)

    async def get_contact_by_phone(self, campaign_id: str, phone_number: str) -> Optional[Dict[str, Any]]:
        def _get():
            self._require_db()
            query = (
                self.db.collection(COLD_CONTACTS)
                .where(filter=FieldFilter("campaign_id", "==", campaign_id))
                .where(filter=FieldFilter("phone_number", "==", phone_number))
                .limit(1)
            )
            docs = list(query.stream())
            if not docs:
                return None
            return docs[0].to_dict()

        return await self._run(_get)

    async def update_contact(self, contact_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await firebase_service.update_document(COLD_CONTACTS, contact_id, updates)

    async def count_contacts_by_status(self, campaign_id: str, statuses: List[str]) -> int:
        def _count():
            self._require_db()
            query = (
                self.db.collection(COLD_CONTACTS)
                .where(filter=FieldFilter("campaign_id", "==", campaign_id))
                .where(filter=FieldFilter("status", "in", statuses))
            )
            return len(list(query.stream()))

        return await self._run(_count)

    async def get_next_contact_for_dial(self, campaign_id: str, now_iso: str) -> Optional[Dict[str, Any]]:
        def _next():
            self._require_db()
            query = (
                self.db.collection(COLD_CONTACTS)
                .where(filter=FieldFilter("campaign_id", "==", campaign_id))
                .where(filter=FieldFilter("status", "in", ["pending", "retry_scheduled"]))
                .where(filter=FieldFilter("next_attempt_at", "<=", now_iso))
                .order_by("next_attempt_at")
                .limit(1)
            )
            docs = list(query.stream())
            if not docs:
                return None
            return docs[0].to_dict()

        return await self._run(_next)

    async def create_attempt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await firebase_service.create_document(COLD_ATTEMPTS, payload["id"], payload)

    async def update_attempt(self, attempt_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await firebase_service.update_document(COLD_ATTEMPTS, attempt_id, updates)

    async def list_attempts(self, campaign_id: str, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        filters = [FieldFilter("campaign_id", "==", campaign_id)]
        return await firebase_service.list_documents(COLD_ATTEMPTS, filters=filters, order_by="created_at", limit=limit, offset=offset)

    async def get_attempt(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        return await firebase_service.get_document(COLD_ATTEMPTS, attempt_id)

    async def get_attempt_by_call_sid(self, twilio_call_sid: str) -> Optional[Dict[str, Any]]:
        def _get():
            self._require_db()
            query = self.db.collection(COLD_ATTEMPTS).where(filter=FieldFilter("twilio_call_sid", "==", twilio_call_sid)).limit(1)
            docs = list(query.stream())
            if not docs:
                return None
            return docs[0].to_dict()

        return await self._run(_get)

    async def count_attempts_for_contact_since(self, contact_id: str, since_iso: str) -> int:
        def _count():
            self._require_db()
            query = (
                self.db.collection(COLD_ATTEMPTS)
                .where(filter=FieldFilter("contact_id", "==", contact_id))
                .where(filter=FieldFilter("created_at", ">=", since_iso))
            )
            return len(list(query.stream()))

        return await self._run(_count)

    async def create_runtime_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await firebase_service.create_document(COLD_EVENTS, payload["id"], payload)

    async def create_dnc_entries_bulk(self, entries: List[Dict[str, Any]]) -> None:
        if not entries:
            return

        def _write():
            self._require_db()
            batch = self.db.batch()
            for entry in entries:
                ref = self.db.collection(COLD_DNC).document(entry["id"])
                batch.set(ref, entry)
            batch.commit()

        await self._run(_write)

    async def create_dnc_entry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await firebase_service.create_document(COLD_DNC, payload["id"], payload)

    async def list_dnc(self, tenant_id: str, limit: int = 2000, offset: int = 0) -> List[Dict[str, Any]]:
        filters = [FieldFilter("tenant_id", "==", tenant_id)]
        return await firebase_service.list_documents(COLD_DNC, filters=filters, order_by="created_at", limit=limit, offset=offset)

    async def is_phone_in_dnc(self, tenant_id: str, phone_number: str) -> bool:
        def _exists():
            self._require_db()
            query = (
                self.db.collection(COLD_DNC)
                .where(filter=FieldFilter("tenant_id", "==", tenant_id))
                .where(filter=FieldFilter("phone_number", "==", phone_number))
                .limit(1)
            )
            docs = list(query.stream())
            return len(docs) > 0

        return await self._run(_exists)

    async def get_dnc_phone_set(self, tenant_id: str) -> set[str]:
        rows = await self.list_dnc(tenant_id=tenant_id, limit=50000, offset=0)
        return {row.get("phone_number", "") for row in rows if row.get("phone_number")}


campaign_repository = CampaignRepository()
