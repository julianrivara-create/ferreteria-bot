#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Live smoke checks for staging/production endpoints."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from typing import Any

import requests


def _print_result(ok: bool, label: str, details: str = "") -> None:
    prefix = "OK" if ok else "FAIL"
    suffix = f" - {details}" if details else ""
    print(f"[{prefix}] {label}{suffix}")


def _expect_status(resp: requests.Response, expected: int, label: str) -> bool:
    ok = resp.status_code == expected
    _print_result(ok, label, f"status={resp.status_code}, expected={expected}")
    return ok


def _meta_signature(secret: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def run_smoke(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    failures = 0

    session = requests.Session()
    session.headers.update({"User-Agent": "sales-bot-platform-staging-smoke/1.0"})

    health = session.get(f"{base}/health", timeout=10)
    if not _expect_status(health, 200, "GET /health"):
        failures += 1

    api_health = session.get(f"{base}/api/health", timeout=10)
    if not _expect_status(api_health, 200, "GET /api/health"):
        failures += 1
    else:
        runtime_stack_ok = api_health.headers.get("X-Runtime-Stack") == "final"
        _print_result(
            runtime_stack_ok,
            "Canonical runtime header",
            f"X-Runtime-Stack={api_health.headers.get('X-Runtime-Stack')}",
        )
        if not runtime_stack_ok:
            failures += 1

    diag = session.get(
        f"{base}/diag/db",
        headers={"X-Admin-Token": args.admin_token},
        timeout=10,
    )
    if not _expect_status(diag, 200, "GET /diag/db"):
        failures += 1
    else:
        diag_json = diag.json()
        diag_redacted = diag_json.get("detail_level") == "redacted"
        _print_result(diag_redacted, "/diag/db redaction", f"detail_level={diag_json.get('detail_level')}")
        if not diag_redacted:
            failures += 1

    catalog = session.get(f"{base}/api/catalog", timeout=15)
    if not _expect_status(catalog, 200, "GET /api/catalog"):
        failures += 1

    grouped = session.get(f"{base}/api/catalog/grouped", timeout=15)
    if not _expect_status(grouped, 200, "GET /api/catalog/grouped"):
        failures += 1

    tenant_products = session.get(f"{base}/api/t/{args.tenant_slug}/products", timeout=15)
    if not _expect_status(tenant_products, 200, "GET /api/t/<tenant>/products"):
        failures += 1

    chat_payload = {"message": "hola", "user": "staging-smoke-user"}
    chat = session.post(f"{base}/api/chat", json=chat_payload, timeout=20)
    chat_ok = _expect_status(chat, 200, "POST /api/chat")
    if not chat_ok:
        failures += 1
    else:
        body = chat.json()
        shaped = body.get("status") == "success" and isinstance(body.get("content"), str)
        _print_result(shaped, "/api/chat response shape", f"keys={sorted(body.keys())}")
        if not shaped:
            failures += 1

    for _ in range(args.rate_limit_per_minute):
        session.post(f"{base}/api/chat", json=chat_payload, timeout=20)
    limited = session.post(f"{base}/api/chat", json=chat_payload, timeout=20)
    limit_ok = limited.status_code == 429 and bool(limited.headers.get("X-RateLimit-Limit"))
    _print_result(limit_ok, "POST /api/chat rate limit", f"status={limited.status_code}")
    if not limit_ok:
        failures += 1

    tenant_chat = session.post(
        f"{base}/api/t/{args.tenant_slug}/chat",
        json={"message": "hola", "user": "tenant-smoke-user"},
        timeout=20,
    )
    if not _expect_status(tenant_chat, 200, "POST /api/t/<tenant>/chat"):
        failures += 1

    if args.channel_provider in {"auto", "meta"}:
        if not args.meta_verify_token:
            _print_result(False, "GET /webhooks/whatsapp verification", "META_VERIFY_TOKEN missing for Meta smoke")
            failures += 1
        else:
            verify = session.get(
                f"{base}/webhooks/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": args.meta_verify_token,
                    "hub.challenge": "smoke-challenge",
                },
                timeout=10,
            )
            verify_ok = verify.status_code == 200 and verify.text == "smoke-challenge"
            _print_result(verify_ok, "GET /webhooks/whatsapp verification", f"status={verify.status_code}")
            if not verify_ok:
                failures += 1

        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.staging-smoke-1",
                                        "from": args.whatsapp_from,
                                        "type": "text",
                                        "text": {"body": "hola"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        webhook_headers = {}
        if args.meta_app_secret:
            webhook_headers["X-Hub-Signature-256"] = _meta_signature(args.meta_app_secret, webhook_payload)
        webhook = session.post(
            f"{base}/webhooks/whatsapp",
            json=webhook_payload,
            headers=webhook_headers,
            timeout=20,
        )
        webhook_ok = webhook.status_code in {200, 202}
        _print_result(webhook_ok, "POST /webhooks/whatsapp", f"status={webhook.status_code}")
        if not webhook_ok:
            failures += 1
    else:
        _print_result(
            True,
            "WhatsApp webhook smoke",
            "Twilio live webhook validation is manual in the canonical runtime release checklist",
        )

    if failures:
        print(f"\nSmoke failed with {failures} issue(s).")
        return 1

    print("\nSmoke passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live staging smoke checks against the canonical runtime.")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. https://my-bot.up.railway.app")
    parser.add_argument("--admin-token", required=True, help="Admin token for /diag/db")
    parser.add_argument("--tenant-slug", default="farmacia", help="Tenant slug to validate storefront routes")
    parser.add_argument(
        "--channel-provider",
        choices=["auto", "meta", "twilio", "none"],
        default="auto",
        help="Which WhatsApp provider should be validated by the smoke run.",
    )
    parser.add_argument("--meta-verify-token", default="", help="Meta verify token for webhook GET validation")
    parser.add_argument("--meta-app-secret", default="", help="Meta app secret for signed webhook POST checks")
    parser.add_argument("--whatsapp-from", default="5491112345678", help="Synthetic sender number for webhook smoke")
    parser.add_argument("--rate-limit-per-minute", type=int, default=60, help="Expected public chat rate limit")
    args = parser.parse_args()
    return run_smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
