"""LiveKit SIP helpers for outbound cold-caller flow."""

from urllib.parse import quote

from app.core.config import settings


def get_livekit_sip_domain() -> str:
    domain = settings.LIVEKIT_SIP_DOMAIN.strip()
    if domain.startswith("sip:"):
        domain = domain[4:]
    if not domain:
        raise ValueError("LIVEKIT_SIP_DOMAIN is not configured")
    return domain


def build_sip_uri(room_name: str, tenant_id: str, call_sid: str, called_number: str) -> str:
    domain = get_livekit_sip_domain()
    query = "&".join(
        [
            f"{settings.LIVEKIT_SIP_HEADER_CALL_ID}={quote(call_sid, safe='')}",
            f"{settings.LIVEKIT_SIP_HEADER_TENANT_ID}={quote(tenant_id, safe='')}",
            f"{settings.LIVEKIT_SIP_HEADER_CALLED_NUMBER}={quote(called_number, safe='')}",
        ]
    )
    return f"sip:{room_name}@{domain}?{query}"

