"""Encryption/decryption helpers compatible with main backend secrets."""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings


class EncryptionService:
    def __init__(self) -> None:
        secret = settings.SECRET_KEY or "development-insecure-secret"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"ai_phone_scheduler_salt",
            iterations=100000,
            backend=default_backend(),
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        self.fernet = Fernet(key)

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        return self.fernet.decrypt(ciphertext.encode()).decode()


encryption_service = EncryptionService()
