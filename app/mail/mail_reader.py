"""Inbox reader — lists unread messages and fetches full parsed content."""

from __future__ import annotations

import base64
import email
import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from typing import Optional

from bs4 import BeautifulSoup

from app.mail.gmail_client import GmailClient
from app.mail.types import MailMetadata, ParsedMail

# Lines that look like quoted-reply separators
_QUOTED_PATTERNS = re.compile(
    r"^(>+\s|On .+wrote:|El .+escribi|[-_]{3,}|From:\s|De:\s)",
    re.MULTILINE | re.IGNORECASE,
)


class MailReader:
    def __init__(self, client: GmailClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_unread(self, max_results: int = 10) -> list[MailMetadata]:
        """Return metadata for up to *max_results* unread messages, newest first."""
        service = self._client.get_service()
        result = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=max_results)
            .execute()
        )
        messages = result.get("messages", [])
        out = []
        for msg_stub in messages:
            meta = self._fetch_metadata(service, msg_stub["id"])
            if meta:
                out.append(meta)
        return out

    def get_full_mail(self, msg_id: str) -> ParsedMail:
        """Fetch and parse a single message by ID."""
        service = self._client.get_service()
        raw = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )
        return self._parse_full(raw)

    # ------------------------------------------------------------------
    # Internal: metadata
    # ------------------------------------------------------------------

    def _fetch_metadata(self, service, msg_id: str) -> Optional[MailMetadata]:
        raw = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="metadata",
                 metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
        from_raw = headers.get("from", "")
        from_name, from_addr = _parse_from(from_raw)
        label_ids = raw.get("labelIds", [])
        ts_ms = int(raw.get("internalDate", 0))
        return MailMetadata(
            id=raw["id"],
            thread_id=raw.get("threadId", ""),
            from_addr=from_addr,
            from_name=from_name,
            subject=_decode_header_value(headers.get("subject", "(sin asunto)")),
            snippet=raw.get("snippet", ""),
            internal_date=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            is_unread="UNREAD" in label_ids,
        )

    # ------------------------------------------------------------------
    # Internal: full parse
    # ------------------------------------------------------------------

    def _parse_full(self, raw: dict) -> ParsedMail:
        headers = {
            h["name"].lower(): h["value"]
            for h in raw.get("payload", {}).get("headers", [])
        }
        from_raw = headers.get("from", "")
        from_name, from_addr = _parse_from(from_raw)
        label_ids = raw.get("labelIds", [])
        ts_ms = int(raw.get("internalDate", 0))

        meta = MailMetadata(
            id=raw["id"],
            thread_id=raw.get("threadId", ""),
            from_addr=from_addr,
            from_name=from_name,
            subject=_decode_header_value(headers.get("subject", "(sin asunto)")),
            snippet=raw.get("snippet", ""),
            internal_date=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
            is_unread="UNREAD" in label_ids,
        )

        body_plain, body_html, attachments_count = _extract_body(raw.get("payload", {}))
        body_plain = _strip_quoted_reply(body_plain)

        refs_raw = headers.get("references", "")
        references = refs_raw.split() if refs_raw else []

        return ParsedMail(
            metadata=meta,
            body_plain=body_plain,
            body_html=body_html,
            attachments_count=attachments_count,
            in_reply_to=headers.get("in-reply-to"),
            references=references,
        )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _parse_from(from_header: str) -> tuple[str, str]:
    """Split 'Name <addr>' into (name, addr). Handles missing name."""
    if "<" in from_header and ">" in from_header:
        name_part, _, addr_part = from_header.rpartition("<")
        name = name_part.strip().strip('"')
        addr = addr_part.rstrip(">").strip()
        return _decode_header_value(name), addr
    return "", from_header.strip()


def _decode_header_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_body(payload: dict) -> tuple[str, Optional[str], int]:
    """Recursively walk MIME parts, return (plain, html, attachment_count)."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments = 0

    def walk(part: dict) -> None:
        nonlocal attachments
        mime = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})
        sub_parts = part.get("parts", [])

        if filename:
            attachments += 1
            return

        if sub_parts:
            for p in sub_parts:
                walk(p)
            return

        data = body.get("data")
        if not data:
            return

        decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

        if mime == "text/plain":
            plain_parts.append(decoded)
        elif mime == "text/html":
            html_parts.append(decoded)

    walk(payload)

    html_combined = "\n".join(html_parts) if html_parts else None

    if plain_parts:
        plain = "\n".join(plain_parts)
    elif html_combined:
        plain = _html_to_text(html_combined)
    else:
        plain = ""

    return plain, html_combined, attachments


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style blobs before extracting text
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _strip_quoted_reply(text: str) -> str:
    """Remove quoted-reply sections from plain text body."""
    lines = text.splitlines()
    clean: list[str] = []
    for line in lines:
        if _QUOTED_PATTERNS.match(line):
            break
        clean.append(line)
    return "\n".join(clean).strip()
