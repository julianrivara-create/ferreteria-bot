"""Unit tests for MailReader — uses fake Gmail API payloads, no network."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.mail.mail_reader import (
    MailReader,
    _html_to_text,
    _parse_from,
    _strip_quoted_reply,
)
from app.mail.types import MailMetadata, ParsedMail


# ---------------------------------------------------------------------------
# Fixtures: fake Gmail API payloads
# ---------------------------------------------------------------------------

def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


PLAIN_BODY = "Hola, quiero cotizar 3 mechas 8mm y 2 llaves francesas.\nGracias."

HTML_BODY = """\
<html><body>
<p>Hola, quiero cotizar:</p>
<ul>
  <li>3 mechas 8mm</li>
  <li>2 llaves francesas</li>
</ul>
<p>Gracias.</p>
</body></html>
"""

QUOTED_BODY = """\
Necesito los precios urgente.

On Mon, 5 May 2026 at 10:00, Vendedor <bot@ferreteria.com> wrote:
> Hola, ¿en qué te puedo ayudar?
"""

MULTIPART_PAYLOAD = {
    "mimeType": "multipart/alternative",
    "headers": [
        {"name": "From", "value": "Juan Perez <juan@example.com>"},
        {"name": "Subject", "value": "Pedido de materiales"},
        {"name": "Date", "value": "Mon, 5 May 2026 10:00:00 +0000"},
        {"name": "In-Reply-To", "value": "<prev@mail.com>"},
        {"name": "References", "value": "<prev@mail.com> <older@mail.com>"},
    ],
    "parts": [
        {"mimeType": "text/plain", "body": {"data": _b64(PLAIN_BODY)}, "filename": ""},
        {"mimeType": "text/html", "body": {"data": _b64(HTML_BODY)}, "filename": ""},
    ],
}

PLAIN_ONLY_PAYLOAD = {
    "mimeType": "text/plain",
    "headers": [
        {"name": "From", "value": "Maria Garcia <maria@example.com>"},
        {"name": "Subject", "value": "=?utf-8?b?UHJlc3VwdWVzdG8=?="},  # "Presupuesto" b64-encoded
    ],
    "body": {"data": _b64(PLAIN_BODY)},
    "filename": "",
}

HTML_ONLY_PAYLOAD = {
    "mimeType": "text/html",
    "headers": [
        {"name": "From", "value": "Carlos <carlos@example.com>"},
        {"name": "Subject", "value": "Consulta HTML"},
    ],
    "body": {"data": _b64(HTML_BODY)},
    "filename": "",
}

QUOTED_REPLY_PAYLOAD = {
    "mimeType": "text/plain",
    "headers": [
        {"name": "From", "value": "cliente@example.com"},
        {"name": "Subject", "value": "Re: Cotizacion"},
    ],
    "body": {"data": _b64(QUOTED_BODY)},
    "filename": "",
}


def _fake_raw_message(msg_id: str, payload: dict, labels=None, snippet="", ts_ms=1746432000000):
    return {
        "id": msg_id,
        "threadId": "thread_" + msg_id,
        "labelIds": labels or ["INBOX", "UNREAD"],
        "snippet": snippet,
        "internalDate": str(ts_ms),
        "payload": payload,
    }


def _make_reader_with_service(service_mock) -> MailReader:
    client = MagicMock()
    client.get_service.return_value = service_mock
    return MailReader(client)


def _build_service_mock(messages: list[dict]) -> MagicMock:
    """Build a mock that returns *messages* from .users().messages().list/.get()."""
    service = MagicMock()
    users = service.users.return_value
    msgs = users.messages.return_value

    list_exec = MagicMock()
    list_exec.execute.return_value = {
        "messages": [{"id": m["id"]} for m in messages]
    }
    msgs.list.return_value = list_exec

    def _get_exec(userId, id, **kwargs):
        for m in messages:
            if m["id"] == id:
                exec_mock = MagicMock()
                exec_mock.execute.return_value = m
                return exec_mock
        raise KeyError(id)

    msgs.get.side_effect = _get_exec
    return service


# ---------------------------------------------------------------------------
# Tests: _parse_from
# ---------------------------------------------------------------------------

class TestParseFrom:
    def test_name_and_addr(self):
        name, addr = _parse_from("Juan Perez <juan@example.com>")
        assert name == "Juan Perez"
        assert addr == "juan@example.com"

    def test_addr_only(self):
        name, addr = _parse_from("juan@example.com")
        assert name == ""
        assert addr == "juan@example.com"

    def test_quoted_name(self):
        name, addr = _parse_from('"Maria Garcia" <maria@example.com>')
        assert name == "Maria Garcia"
        assert addr == "maria@example.com"


# ---------------------------------------------------------------------------
# Tests: _html_to_text
# ---------------------------------------------------------------------------

class TestHtmlToText:
    def test_strips_tags(self):
        text = _html_to_text("<p>Hola <b>mundo</b></p>")
        assert "Hola" in text
        assert "mundo" in text
        assert "<" not in text

    def test_removes_scripts(self):
        text = _html_to_text("<script>alert(1)</script><p>OK</p>")
        assert "alert" not in text
        assert "OK" in text

    def test_list_items_appear(self):
        text = _html_to_text(HTML_BODY)
        assert "mechas" in text.lower()
        assert "llaves" in text.lower()


# ---------------------------------------------------------------------------
# Tests: _strip_quoted_reply
# ---------------------------------------------------------------------------

class TestStripQuotedReply:
    def test_strips_gmail_quote(self):
        result = _strip_quoted_reply(QUOTED_BODY)
        assert "Necesito los precios" in result
        assert "Hola, ¿en qué te puedo ayudar?" not in result

    def test_plain_message_unchanged(self):
        result = _strip_quoted_reply(PLAIN_BODY)
        assert "3 mechas" in result


# ---------------------------------------------------------------------------
# Tests: MailReader.list_unread
# ---------------------------------------------------------------------------

class TestListUnread:
    def test_returns_metadata_list(self):
        msg = _fake_raw_message("msg1", PLAIN_ONLY_PAYLOAD, snippet="Pedido")
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        results = reader.list_unread(max_results=5)
        assert len(results) == 1
        meta = results[0]
        assert meta.id == "msg1"
        assert meta.from_addr == "maria@example.com"
        assert meta.is_unread is True

    def test_empty_inbox(self):
        service = MagicMock()
        service.users().messages().list().execute.return_value = {}
        reader = _make_reader_with_service(service)
        assert reader.list_unread() == []

    def test_datetime_parsed_correctly(self):
        ts = 1777939200000  # 2026-05-05 00:00:00 UTC
        msg = _fake_raw_message("msg2", PLAIN_ONLY_PAYLOAD, ts_ms=ts)
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        results = reader.list_unread()
        assert results[0].internal_date == datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tests: MailReader.get_full_mail
# ---------------------------------------------------------------------------

class TestGetFullMail:
    def test_plain_only_mail(self):
        msg = _fake_raw_message("plain1", PLAIN_ONLY_PAYLOAD)
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        parsed = reader.get_full_mail("plain1")
        assert isinstance(parsed, ParsedMail)
        assert "mechas" in parsed.body_plain
        assert parsed.attachments_count == 0
        assert parsed.in_reply_to is None

    def test_html_only_body_converted_to_plain(self):
        msg = _fake_raw_message("html1", HTML_ONLY_PAYLOAD)
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        parsed = reader.get_full_mail("html1")
        assert "mechas" in parsed.body_plain.lower()
        assert "<" not in parsed.body_plain  # no HTML tags

    def test_multipart_prefers_plain_part(self):
        msg = _fake_raw_message("mp1", MULTIPART_PAYLOAD)
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        parsed = reader.get_full_mail("mp1")
        assert "mechas" in parsed.body_plain
        assert parsed.body_html is not None
        assert "<ul>" in parsed.body_html

    def test_threading_fields(self):
        msg = _fake_raw_message("mp1", MULTIPART_PAYLOAD)
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        parsed = reader.get_full_mail("mp1")
        assert parsed.in_reply_to == "<prev@mail.com>"
        assert "<prev@mail.com>" in parsed.references
        assert "<older@mail.com>" in parsed.references

    def test_quoted_reply_stripped(self):
        msg = _fake_raw_message("qr1", QUOTED_REPLY_PAYLOAD)
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        parsed = reader.get_full_mail("qr1")
        assert "Necesito los precios" in parsed.body_plain
        assert "Hola, ¿en qué te puedo ayudar?" not in parsed.body_plain

    def test_attachment_counted(self):
        payload_with_attachment = {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "x@x.com"},
                {"name": "Subject", "value": "Con adjunto"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("Ver adjunto")}, "filename": ""},
                {"mimeType": "application/pdf", "filename": "lista.pdf", "body": {"size": 1234}},
            ],
        }
        msg = _fake_raw_message("att1", payload_with_attachment)
        service = _build_service_mock([msg])
        reader = _make_reader_with_service(service)
        parsed = reader.get_full_mail("att1")
        assert parsed.attachments_count == 1
