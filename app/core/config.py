"""Application configuration."""

from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8010

    # Auth
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"

    # Firebase
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_PRIVATE_KEY: str = ""
    FIREBASE_CLIENT_EMAIL: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CALL_CONFIG_TTL_SECONDS: int = 3600

    # Twilio / LiveKit
    TWILIO_WEBHOOK_BASE_URL: str = ""
    LIVEKIT_SIP_DOMAIN: str = ""
    LIVEKIT_SIP_HEADER_TENANT_ID: str = "X-LK-TenantId"
    LIVEKIT_SIP_HEADER_CALL_ID: str = "X-LK-CallId"
    LIVEKIT_SIP_HEADER_CALLED_NUMBER: str = "X-LK-CalledNumber"

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_PUBLIC_BASE_URL: str = ""
    PRESIGNED_URL_EXPIRES_SECONDS: int = 900
    MAX_AUDIO_UPLOAD_MB: int = 10

    # Defaults
    DEFAULT_TIMEZONE: str = "UTC"
    DEFAULT_WINDOW_START: str = "09:00"
    DEFAULT_WINDOW_END: str = "18:00"
    DEFAULT_MAX_ATTEMPTS_PER_CONTACT: int = 3
    DEFAULT_MAX_ATTEMPTS_PER_DAY: int = 1
    DEFAULT_RETRY_DELAY_MINUTES: int = 10
    DEFAULT_RETRY_BUSY_NOANSWER: int = 2
    CAMPAIGN_LEASE_SECONDS: int = 90

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _parse_debug(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        parsed = str(value).strip().lower()
        if parsed in {"1", "true", "yes", "on", "debug", "development", "dev"}:
            return True
        if parsed in {"0", "false", "no", "off", "release", "production", "prod"}:
            return False
        return bool(parsed)

    def firebase_private_key(self) -> str:
        return self.FIREBASE_PRIVATE_KEY.replace("\\n", "\n")

    @property
    def twilio_base_url(self) -> str:
        return self.TWILIO_WEBHOOK_BASE_URL.rstrip("/")

    def s3_public_url(self, object_key: str) -> str:
        if self.S3_PUBLIC_BASE_URL:
            return f"{self.S3_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
        endpoint = self.S3_ENDPOINT_URL.rstrip("/") if self.S3_ENDPOINT_URL else f"https://s3.{self.AWS_REGION}.amazonaws.com"
        return f"{endpoint}/{self.S3_BUCKET}/{object_key}"

    @property
    def has_s3_config(self) -> bool:
        return bool(self.S3_BUCKET and self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)

    @property
    def has_firebase_config(self) -> bool:
        return bool(self.FIREBASE_PROJECT_ID and self.FIREBASE_PRIVATE_KEY and self.FIREBASE_CLIENT_EMAIL)

    @property
    def has_auth_config(self) -> bool:
        return bool(self.SECRET_KEY)

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"


settings = Settings()
