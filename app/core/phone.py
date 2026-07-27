"""Phone normalization helpers."""

import re


def normalize_phone_number(phone_number: str) -> str:
    if not phone_number:
        raise ValueError("Phone number is required")

    cleaned = re.sub(r"[^\d+]", "", phone_number.strip())
    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"
    if not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"

    digits = cleaned[1:]
    if not digits.isdigit() or len(digits) < 10 or len(digits) > 15:
        raise ValueError(f"Invalid phone number format: {phone_number}")
    return cleaned


def normalize_phone_number_safe(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    try:
        return normalize_phone_number(phone_number)
    except ValueError:
        return None

