"""Gmail OAuth client — installed-app flow with automatic token refresh."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# gmail.modify lets us mark messages as read (M1+). readonly is not enough.
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailAuthError(Exception):
    pass


class GmailClient:
    """Wraps OAuth flow and returns an authorised Gmail API service."""

    def __init__(
        self,
        credentials_path: str | Path = "credentials.json",
        token_path: str | Path = "token.json",
    ) -> None:
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self._service = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Run the OAuth installed-app flow, persisting the token to disk."""
        creds = self._load_token()
        if creds and creds.valid:
            return
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_token(creds)
                return
            except RefreshError:
                # Token revoked or scopes changed — re-run full flow.
                pass

        if not self.credentials_path.exists():
            raise GmailAuthError(
                f"credentials.json not found at {self.credentials_path}. "
                "Follow docs/MAIL_SETUP.md to download it from Google Cloud Console."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_path), _SCOPES
        )
        creds = flow.run_local_server(port=0)
        self._save_token(creds)

    def get_service(self):
        """Return a cached, authenticated Gmail API service resource."""
        if self._service is not None:
            return self._service

        creds = self._load_token()
        if creds is None or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self._save_token(creds)
                except RefreshError:
                    raise GmailAuthError(
                        "Token expired and refresh failed. Run: python -m app.mail login"
                    )
            else:
                raise GmailAuthError(
                    "Not authenticated. Run: python -m app.mail login"
                )

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def logout(self) -> None:
        """Delete the stored token, forcing re-authentication on next use."""
        if self.token_path.exists():
            self.token_path.unlink()
        self._service = None

    @property
    def is_authenticated(self) -> bool:
        creds = self._load_token()
        return creds is not None and creds.valid

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_token(self) -> Optional[Credentials]:
        if not self.token_path.exists():
            return None
        try:
            return Credentials.from_authorized_user_file(str(self.token_path), _SCOPES)
        except (ValueError, KeyError):
            return None

    def _save_token(self, creds: Credentials) -> None:
        self.token_path.write_text(creds.to_json())
