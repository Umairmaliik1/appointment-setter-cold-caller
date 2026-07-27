"""Campaign schemas."""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


CAMPAIGN_STATUS = Literal["draft", "ready", "running", "paused", "completed", "canceled", "failed"]
CONTACT_STATUS = Literal[
    "pending",
    "calling",
    "completed",
    "failed",
    "dnc_skipped",
    "retry_scheduled",
    "canceled",
]


class IntroAudioInfo(BaseModel):
    object_key: str
    url: str
    content_type: str
    file_name: str
    confirmed: bool = False
    uploaded_at: Optional[str] = None


class CampaignComplianceConfig(BaseModel):
    timezone: str = Field(default="UTC", min_length=2, max_length=64)
    call_window_start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    call_window_end: str = Field(default="18:00", pattern=r"^\d{2}:\d{2}$")
    max_attempts_per_contact: int = Field(default=3, ge=1, le=10)
    max_attempts_per_day: int = Field(default=1, ge=1, le=5)
    retry_delay_minutes: int = Field(default=10, ge=1, le=1440)
    retry_on_statuses: List[str] = Field(default_factory=lambda: ["busy", "no-answer"])
    excluded_numbers: List[str] = Field(default_factory=list, max_length=2000)

    @field_validator("retry_on_statuses")
    @classmethod
    def validate_retry_statuses(cls, value: List[str]) -> List[str]:
        allowed = {"busy", "no-answer", "failed"}
        cleaned = [item.strip().lower() for item in value if item and item.strip()]
        for status in cleaned:
            if status not in allowed:
                raise ValueError(f"Unsupported retry status: {status}")
        return list(dict.fromkeys(cleaned))


class CampaignCreateRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=150)
    description: str = Field(default="", max_length=2000)
    voice_agent_id: str = Field(..., min_length=1)
    outbound_phone_number_id: str = Field(..., min_length=1)
    recording_enabled: bool = False
    recording_disclosure: str = Field(default="", max_length=500)
    compliance: CampaignComplianceConfig = Field(default_factory=CampaignComplianceConfig)


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)
    voice_agent_id: Optional[str] = Field(None, min_length=1)
    outbound_phone_number_id: Optional[str] = Field(None, min_length=1)
    recording_enabled: Optional[bool] = None
    recording_disclosure: Optional[str] = Field(None, max_length=500)
    compliance: Optional[CampaignComplianceConfig] = None


class OutboundPhoneNumberInfo(BaseModel):
    id: str
    phone_number: str
    usage_role: str
    role_status: str


class CampaignResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str
    voice_agent_id: str
    outbound_phone_number_id: Optional[str] = None
    outbound_phone_number: Optional[OutboundPhoneNumberInfo] = None
    status: CAMPAIGN_STATUS
    recording_enabled: bool
    recording_disclosure: str
    compliance: CampaignComplianceConfig
    intro_audio: Optional[IntroAudioInfo] = None
    total_contacts: int = 0
    completed_contacts: int = 0
    failed_contacts: int = 0
    dnc_contacts: int = 0
    in_progress_contacts: int = 0
    created_by: str
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    active_contact_id: Optional[str] = None
    active_call_sid: Optional[str] = None


class CampaignContactResponse(BaseModel):
    id: str
    campaign_id: str
    tenant_id: str
    phone_number: str
    name: Optional[str] = None
    notes: Optional[str] = None
    status: CONTACT_STATUS
    attempt_count: int
    next_attempt_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    last_outcome: Optional[str] = None
    created_at: str
    updated_at: str


class CampaignAttemptResponse(BaseModel):
    id: str
    campaign_id: str
    contact_id: str
    tenant_id: str
    twilio_call_sid: Optional[str] = None
    attempt_number: int
    status: str
    answered_by: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[int] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None


class ContactUploadRejectedItem(BaseModel):
    row_number: int
    phone_number: Optional[str]
    reason: str


class ContactUploadResponse(BaseModel):
    campaign_id: str
    accepted_count: int
    rejected_count: int
    total_rows: int
    rejected: List[ContactUploadRejectedItem]


class IntroAudioUploadUrlRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)


class IntroAudioUploadUrlResponse(BaseModel):
    campaign_id: str
    upload_url: str
    object_key: str
    public_url: str
    expires_in_seconds: int


class IntroAudioConfirmRequest(BaseModel):
    object_key: str
    file_name: str
    content_type: str
    public_url: Optional[str] = None


class CampaignControlResponse(BaseModel):
    campaign_id: str
    status: CAMPAIGN_STATUS
    message: str
