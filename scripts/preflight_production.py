#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Preflight checks for staging/production promotion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def _status(ok: bool, label: str, detail: str = "") -> str:
    prefix = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    return f"[{prefix}] {label}{suffix}"


def _warn(label: str, detail: str = "") -> str:
    suffix = f" - {detail}" if detail else ""
    return f"[WARN] {label}{suffix}"


def _is_configured(value: str | None) -> bool:
    return bool((value or "").strip())


def _whatsapp_provider_status(settings, provider: str) -> tuple[bool, str]:
    if provider == "none":
        return True, "channel validation skipped"

    meta_fields = {
        "META_VERIFY_TOKEN": settings.is_secret_configured(settings.META_VERIFY_TOKEN),
        "META_ACCESS_TOKEN": settings.is_secret_configured(settings.META_ACCESS_TOKEN),
        "WHATSAPP_PHONE_NUMBER_ID": _is_configured(settings.WHATSAPP_PHONE_NUMBER_ID),
    }
    twilio_fields = {
        "TWILIO_ACCOUNT_SID": _is_configured(getattr(settings, "TWILIO_ACCOUNT_SID", "")),
        "TWILIO_AUTH_TOKEN": _is_configured(getattr(settings, "TWILIO_AUTH_TOKEN", "")),
        "TWILIO_WHATSAPP_NUMBER": _is_configured(getattr(settings, "TWILIO_WHATSAPP_NUMBER", "")),
    }

    if provider == "meta":
        missing = [name for name, ok in meta_fields.items() if not ok]
        return (not missing, "configured" if not missing else "missing: " + ", ".join(missing))

    if provider == "twilio":
        missing = [name for name, ok in twilio_fields.items() if not ok]
        return (not missing, "configured" if not missing else "missing: " + ", ".join(missing))

    meta_ready = all(meta_fields.values())
    twilio_ready = all(twilio_fields.values())
    meta_partial = any(meta_fields.values()) and not meta_ready
    twilio_partial = any(twilio_fields.values()) and not twilio_ready

    if meta_ready:
        return True, "configured via Meta"
    if twilio_ready:
        return True, "configured via Twilio"
    if meta_partial:
        missing = [name for name, ok in meta_fields.items() if not ok]
        return False, "partial Meta config: missing " + ", ".join(missing)
    if twilio_partial:
        missing = [name for name, ok in twilio_fields.items() if not ok]
        return False, "partial Twilio config: missing " + ", ".join(missing)
    return False, "configure Meta or Twilio before validating live channel traffic"


def run_preflight(mode: str, *, channel_provider: str = "auto") -> int:
    settings = get_settings()
    failures: list[str] = []
    warnings: list[str] = []

    required_checks: Iterable[tuple[str, bool, str]] = [
        ("DATABASE_URL", bool((settings.DATABASE_URL or "").strip()), settings.DATABASE_URL),
        ("SECRET_KEY", settings.is_secret_configured(settings.SECRET_KEY), settings.SECRET_KEY),
        ("ADMIN_TOKEN", settings.is_secret_configured(settings.ADMIN_TOKEN), settings.ADMIN_TOKEN),
    ]

    print(f"Preflight mode: {mode}")
    print(f"Environment: {settings.ENVIRONMENT}")
    print()

    for label, ok, value in required_checks:
        detail = "configured" if ok else "missing or insecure"
        line = _status(ok, label, detail)
        print(line)
        if not ok:
            failures.append(line)

    openai_ok = settings.is_secret_configured(settings.OPENAI_API_KEY)
    if mode == "production":
        line = _status(openai_ok, "OPENAI_API_KEY", "required for production")
        print(line)
        if not openai_ok:
            failures.append(line)
    else:
        line = _warn("OPENAI_API_KEY", "recommended for staging" if not openai_ok else "configured")
        print(line)
        if not openai_ok:
            warnings.append(line)

    redis_ok = bool((settings.REDIS_URL or "").strip())
    line = _warn("REDIS_URL", "recommended" if not redis_ok else "configured")
    print(line)
    if not redis_ok:
        warnings.append(line)

    rate_limit = max(1, int(getattr(settings, "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", 60)))
    print(_status(True, "PUBLIC_CHAT_RATE_LIMIT_PER_MINUTE", f"{rate_limit} req/min"))

    provider_ok, provider_detail = _whatsapp_provider_status(settings, channel_provider)
    if provider_ok:
        print(_status(True, "WhatsApp provider config", provider_detail))
    else:
        line = _warn("WhatsApp provider config", provider_detail)
        print(line)
        warnings.append(line)

    runtime_provider = getattr(settings, "whatsapp_provider", "mock")
    print(_status(True, "Runtime provider selection", runtime_provider))

    print()
    if failures:
        print("Preflight result: BLOCKED")
        print(f"Blocking issues: {len(failures)}")
        return 1

    print("Preflight result: READY")
    if warnings:
        print(f"Warnings: {len(warnings)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for staging/production promotion.")
    parser.add_argument(
        "--mode",
        choices=["staging", "production"],
        default="staging",
        help="Validation strictness. Production requires OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--channel-provider",
        choices=["auto", "meta", "twilio", "none"],
        default="auto",
        help="Which WhatsApp provider should be considered for live-channel validation.",
    )
    args = parser.parse_args()
    return run_preflight(args.mode, channel_provider=args.channel_provider)


if __name__ == "__main__":
    raise SystemExit(main())
