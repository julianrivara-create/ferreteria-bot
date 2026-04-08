from __future__ import annotations

import re


E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


def normalize_phone_e164(phone: str | None) -> str | None:
    if phone is None:
        return None

    raw = phone.strip()
    if not raw:
        return None

    if raw.startswith("00"):
        raw = f"+{raw[2:]}"

    if raw.startswith("+"):
        digits = re.sub(r"\D", "", raw[1:])
        normalized = f"+{digits}"
    else:
        digits = re.sub(r"\D", "", raw)
        normalized = f"+{digits}"

    if not E164_PATTERN.match(normalized):
        raise ValueError("phone must be a valid E.164 number")

    return normalized
