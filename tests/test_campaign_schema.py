import pytest
from pydantic import ValidationError

from app.api.v1.schemas.campaign import CampaignComplianceConfig


def test_campaign_compliance_accepts_valid_retry_statuses():
    cfg = CampaignComplianceConfig(retry_on_statuses=["busy", "no-answer"])
    assert cfg.retry_on_statuses == ["busy", "no-answer"]


def test_campaign_compliance_rejects_invalid_retry_status():
    with pytest.raises(ValidationError):
        CampaignComplianceConfig(retry_on_statuses=["busy", "foobar"])

