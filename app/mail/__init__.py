"""Mail channel — M0 scaffolding: Gmail OAuth client + inbox reader."""

from app.mail.gmail_client import GmailClient
from app.mail.mail_reader import MailReader
from app.mail.types import MailMetadata, ParsedMail

__all__ = ["GmailClient", "MailReader", "MailMetadata", "ParsedMail"]
