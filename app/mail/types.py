"""Dataclasses for the mail channel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MailMetadata:
    id: str
    thread_id: str
    from_addr: str
    from_name: str
    subject: str
    snippet: str
    internal_date: datetime
    is_unread: bool


@dataclass
class ParsedMail:
    metadata: MailMetadata
    body_plain: str
    body_html: Optional[str]
    attachments_count: int
    in_reply_to: Optional[str]
    references: list[str] = field(default_factory=list)
