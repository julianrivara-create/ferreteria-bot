from __future__ import annotations

from flask import Flask

from app.crm.api.auth import _rate_limit_ip


def test_rate_limit_ip_ignores_spoofed_forwarded_headers_for_direct_requests():
    app = Flask(__name__)
    with app.test_request_context(
        headers={
            "X-Forwarded-For": "198.51.100.10",
            "X-Real-IP": "198.51.100.11",
            "CF-Connecting-IP": "198.51.100.12",
        },
        environ_base={"REMOTE_ADDR": "8.8.8.8"},
    ):
        assert _rate_limit_ip() == "8.8.8.8"


def test_rate_limit_ip_uses_forwarded_chain_from_trusted_proxy(monkeypatch):
    app = Flask(__name__)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    with app.test_request_context(
        headers={"X-Forwarded-For": "198.51.100.10, 198.51.100.11"},
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
    ):
        assert _rate_limit_ip() == "198.51.100.11"
