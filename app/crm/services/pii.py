from __future__ import annotations

import re


EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
PHONE_PATTERN = re.compile(r"\+?\d[\d\-\s]{6,}\d")


def mask_email(text: str) -> str:
    def _replace(match):
        local = match.group(1)
        domain = match.group(2)
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = local[:2] + "*" * max(1, len(local) - 2)
        return f"{masked_local}@{domain}"

    return EMAIL_PATTERN.sub(_replace, text)


def mask_phone(text: str) -> str:
    def _replace(match):
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 4:
            return "****"
        return "*" * (len(digits) - 4) + digits[-4:]

    return PHONE_PATTERN.sub(_replace, text)


def mask_pii(text: str) -> str:
    return mask_phone(mask_email(text))
