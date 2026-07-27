"""Auth dependencies compatible with existing platform JWTs."""

from typing import Dict, Optional

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings
from app.services.firebase import firebase_service


async def get_current_user_from_token(authorization: Optional[str] = Header(None)) -> Dict:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    token_parts = authorization.split(" ")
    if len(token_parts) != 2 or token_parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format")
    token = token_parts[1]

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    user = await firebase_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return user


def verify_tenant_access(user: Dict, tenant_id: str) -> None:
    role = user.get("role", "user")
    if role == "admin":
        return
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for tenant")


def require_admin(user: Dict = Depends(get_current_user_from_token)) -> Dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def _resolve_allowed_app_ids(user: Dict) -> list[str]:
    explicit = user.get("allowed_app_ids")
    if isinstance(explicit, list) and explicit:
        return [str(app_id).strip() for app_id in explicit if str(app_id).strip()]
    if str(user.get("role", "user")).lower() == "admin":
        return ["appointment_setter", "chatbot_agents"]
    return ["appointment_setter"]


def require_app_access(app_id: str):
    async def dependency(current_user: Dict = Depends(get_current_user_from_token)) -> Dict:
        if str(current_user.get("role", "user")).lower() != "admin" and app_id not in _resolve_allowed_app_ids(current_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access denied: {app_id} is not assigned to this account")
        return current_user

    return dependency

