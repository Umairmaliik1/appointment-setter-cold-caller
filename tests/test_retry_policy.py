from app.services.compliance import compliance_service


def test_retry_policy_allows_busy_when_under_limit():
    campaign = {"compliance": {"retry_on_statuses": ["busy", "no-answer"], "max_attempts_per_contact": 3}}
    contact = {"attempt_count": 1}
    assert compliance_service.can_retry(campaign, contact, "busy") is True


def test_retry_policy_blocks_when_limit_reached():
    campaign = {"compliance": {"retry_on_statuses": ["busy", "no-answer"], "max_attempts_per_contact": 2}}
    contact = {"attempt_count": 2}
    assert compliance_service.can_retry(campaign, contact, "busy") is False

