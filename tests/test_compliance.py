from datetime import datetime, timezone

from app.services.compliance import compliance_service


def test_compliance_within_window_utc():
    campaign = {
        "compliance": {
            "timezone": "UTC",
            "call_window_start": "09:00",
            "call_window_end": "18:00",
        }
    }
    now = datetime(2026, 3, 17, 10, 30, tzinfo=timezone.utc)
    result = compliance_service.is_within_call_window(campaign, now)
    assert result.allowed is True


def test_compliance_outside_window_utc():
    campaign = {
        "compliance": {
            "timezone": "UTC",
            "call_window_start": "09:00",
            "call_window_end": "18:00",
        }
    }
    now = datetime(2026, 3, 17, 23, 30, tzinfo=timezone.utc)
    result = compliance_service.is_within_call_window(campaign, now)
    assert result.allowed is False
    assert "Outside campaign calling window" in result.reason

