"""S3-compatible storage service for intro audio uploads."""

from __future__ import annotations

import os
import uuid
from typing import Dict

import boto3

from app.core.config import settings


class StorageService:
    def __init__(self) -> None:
        self.s3 = None

    def _client(self):
        if self.s3 is None:
            self.s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
                region_name=settings.AWS_REGION,
                endpoint_url=settings.S3_ENDPOINT_URL or None,
            )
        return self.s3

    def build_object_key(self, tenant_id: str, campaign_id: str, file_name: str) -> str:
        ext = os.path.splitext(file_name)[1].lower()
        return f"cold-caller/{tenant_id}/{campaign_id}/{uuid.uuid4().hex}{ext}"

    def generate_upload_url(self, tenant_id: str, campaign_id: str, file_name: str, content_type: str) -> Dict[str, str]:
        if not settings.S3_BUCKET:
            raise ValueError("S3_BUCKET is not configured")
        object_key = self.build_object_key(tenant_id=tenant_id, campaign_id=campaign_id, file_name=file_name)
        upload_url = self._client().generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.S3_BUCKET,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=settings.PRESIGNED_URL_EXPIRES_SECONDS,
        )
        return {
            "object_key": object_key,
            "upload_url": upload_url,
            "public_url": settings.s3_public_url(object_key),
        }

    def confirm_object_exists(self, object_key: str) -> bool:
        try:
            self._client().head_object(Bucket=settings.S3_BUCKET, Key=object_key)
            return True
        except Exception:
            return False


storage_service = StorageService()
