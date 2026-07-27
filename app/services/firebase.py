"""Firebase Firestore service."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.config import settings


class FirebaseService:
    def __init__(self) -> None:
        self.db = None
        if settings.has_firebase_config:
            if not firebase_admin._apps:
                cred = credentials.Certificate(
                    {
                        "type": "service_account",
                        "project_id": settings.FIREBASE_PROJECT_ID,
                        "private_key": settings.firebase_private_key(),
                        "client_email": settings.FIREBASE_CLIENT_EMAIL,
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                )
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()
        self.executor = ThreadPoolExecutor(max_workers=16)

    def _require_db(self):
        if self.db is None:
            raise RuntimeError("Firebase is not configured")

    async def _run(self, fn):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, fn)

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            self._require_db()
            doc = self.db.collection("users").document(user_id).get()
            return doc.to_dict() if doc.exists else None

        return await self._run(_get)

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            self._require_db()
            doc = self.db.collection("agents").document(agent_id).get()
            return doc.to_dict() if doc.exists else None

        return await self._run(_get)

    async def get_twilio_integration(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            self._require_db()
            ref = self.db.collection("twilio_integrations")
            query = ref.where(filter=FieldFilter("tenant_id", "==", tenant_id)).limit(1)
            docs = list(query.stream())
            if not docs:
                return None
            return docs[0].to_dict()

        return await self._run(_get)

    async def get_phone_number(self, phone_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            self._require_db()
            doc = self.db.collection("phone_numbers").document(phone_id).get()
            return doc.to_dict() if doc.exists else None

        return await self._run(_get)

    async def list_phone_numbers_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        def _list():
            self._require_db()
            ref = self.db.collection("phone_numbers")
            query = ref.where(filter=FieldFilter("tenant_id", "==", tenant_id))
            return [doc.to_dict() for doc in query.stream()]

        return await self._run(_list)

    async def create_document(self, collection: str, doc_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        def _create():
            self._require_db()
            self.db.collection(collection).document(doc_id).set(payload)
            return payload

        return await self._run(_create)

    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        def _get():
            self._require_db()
            doc = self.db.collection(collection).document(doc_id).get()
            return doc.to_dict() if doc.exists else None

        return await self._run(_get)

    async def update_document(self, collection: str, doc_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        def _update():
            self._require_db()
            ref = self.db.collection(collection).document(doc_id)
            if not ref.get().exists:
                return None
            ref.update(updates)
            return ref.get().to_dict()

        return await self._run(_update)

    async def list_documents(
        self,
        collection: str,
        filters: Optional[List[FieldFilter]] = None,
        order_by: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        def _query():
            self._require_db()
            query = self.db.collection(collection)
            for condition in filters or []:
                query = query.where(filter=condition)
            if order_by:
                query = query.order_by(order_by)
            query = query.offset(offset).limit(limit)
            return [doc.to_dict() for doc in query.stream()]

        return await self._run(_query)

    async def stream_documents(
        self,
        collection: str,
        filters: Optional[List[FieldFilter]] = None,
        order_by: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        def _query():
            self._require_db()
            query = self.db.collection(collection)
            for condition in filters or []:
                query = query.where(filter=condition)
            if order_by:
                query = query.order_by(order_by)
            query = query.limit(limit)
            return [doc.to_dict() for doc in query.stream()]

        return await self._run(_query)

    async def delete_document(self, collection: str, doc_id: str) -> bool:
        def _delete():
            self._require_db()
            ref = self.db.collection(collection).document(doc_id)
            if not ref.get().exists:
                return False
            ref.delete()
            return True

        return await self._run(_delete)


firebase_service = FirebaseService()
