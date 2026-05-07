"""CLI entry point for the mail channel.

Usage:
    python -m app.mail login
    python -m app.mail list-unread
    python -m app.mail show <msg_id>
    python -m app.mail logout
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

# Resolve credential paths from env vars or repo-root defaults.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CREDENTIALS = _REPO_ROOT / "credentials.json"
_DEFAULT_TOKEN = _REPO_ROOT / "token.json"

CREDENTIALS_PATH = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", _DEFAULT_CREDENTIALS))
TOKEN_PATH = Path(os.environ.get("GMAIL_TOKEN_PATH", _DEFAULT_TOKEN))


def _make_client():
    from app.mail.gmail_client import GmailClient
    return GmailClient(credentials_path=CREDENTIALS_PATH, token_path=TOKEN_PATH)


def cmd_login(args) -> None:
    client = _make_client()
    print(f"Looking for credentials at: {CREDENTIALS_PATH}")
    client.authenticate()
    print("Authentication successful. Token saved to:", TOKEN_PATH)


def cmd_list_unread(args) -> None:
    from app.mail.mail_reader import MailReader
    client = _make_client()
    reader = MailReader(client)
    messages = reader.list_unread(max_results=10)
    if not messages:
        print("No unread messages.")
        return
    print(f"{'ID':<20} {'FROM':<35} {'SUBJECT'}")
    print("-" * 90)
    for m in messages:
        from_display = f"{m.from_name} <{m.from_addr}>" if m.from_name else m.from_addr
        subj = m.subject[:45] if len(m.subject) > 45 else m.subject
        print(f"{m.id:<20} {from_display[:35]:<35} {subj}")
        if m.snippet:
            print(f"    {textwrap.shorten(m.snippet, width=80)}")


def cmd_show(args) -> None:
    from app.mail.mail_reader import MailReader
    client = _make_client()
    reader = MailReader(client)
    mail = reader.get_full_mail(args.msg_id)
    m = mail.metadata
    from_display = f"{m.from_name} <{m.from_addr}>" if m.from_name else m.from_addr
    print(f"ID:       {m.id}")
    print(f"Thread:   {m.thread_id}")
    print(f"From:     {from_display}")
    print(f"Subject:  {m.subject}")
    print(f"Date:     {m.internal_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Unread:   {m.is_unread}")
    print(f"Attchs:   {mail.attachments_count}")
    if mail.in_reply_to:
        print(f"Reply-To: {mail.in_reply_to}")
    print()
    print("--- BODY (plain, max 2000 chars) ---")
    print(mail.body_plain[:2000])
    if len(mail.body_plain) > 2000:
        print(f"\n[... {len(mail.body_plain) - 2000} more chars truncated]")


def cmd_logout(args) -> None:
    client = _make_client()
    client.logout()
    print(f"Token removed: {TOKEN_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.mail",
        description="Ferretería bot — mail channel CLI (M0)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Run OAuth flow and save token")
    sub.add_parser("list-unread", help="List up to 10 unread messages")

    show_p = sub.add_parser("show", help="Show a full message")
    show_p.add_argument("msg_id", help="Gmail message ID (from list-unread)")

    sub.add_parser("logout", help="Delete saved token")

    args = parser.parse_args()

    dispatch = {
        "login": cmd_login,
        "list-unread": cmd_list_unread,
        "show": cmd_show,
        "logout": cmd_logout,
    }
    try:
        dispatch[args.command](args)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
