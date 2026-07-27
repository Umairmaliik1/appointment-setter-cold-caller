from app.core.config import settings
from app.services.twilio_service import twilio_service


def test_twiML_plays_intro_before_dial(monkeypatch):
    monkeypatch.setattr(settings, "LIVEKIT_SIP_DOMAIN", "example.sip.livekit.cloud")
    campaign = {
        "tenant_id": "tenant-1",
        "intro_audio": {"url": "https://cdn.example.com/intro.mp3"},
    }
    response = twilio_service.build_play_then_bridge_twiml(
        campaign=campaign,
        call_sid="CA123",
        to_number="+14155550123",
        room_name="cold-room-1",
        answered_by="human",
    )
    xml = str(response)
    assert "<Play>https://cdn.example.com/intro.mp3</Play>" in xml
    assert "<Dial>" in xml
    assert xml.index("<Play>") < xml.index("<Dial>")


def test_twiML_hangsup_on_machine_answer(monkeypatch):
    monkeypatch.setattr(settings, "LIVEKIT_SIP_DOMAIN", "example.sip.livekit.cloud")
    campaign = {
        "tenant_id": "tenant-1",
        "intro_audio": {"url": "https://cdn.example.com/intro.mp3"},
    }
    response = twilio_service.build_play_then_bridge_twiml(
        campaign=campaign,
        call_sid="CA123",
        to_number="+14155550123",
        room_name="cold-room-1",
        answered_by="machine_start",
    )
    xml = str(response)
    assert "<Hangup" in xml
    assert "<Dial>" not in xml
