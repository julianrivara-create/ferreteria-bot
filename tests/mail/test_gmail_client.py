"""Unit tests for GmailClient — all Google API calls are mocked."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.mail.gmail_client import GmailClient, GmailAuthError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_creds():
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "rt"
    creds.to_json.return_value = json.dumps({"token": "t", "refresh_token": "rt"})
    return creds


def _make_expired_creds(refresh_ok: bool = True):
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "rt" if refresh_ok else None

    def _refresh(req):
        creds.valid = True
        creds.expired = False

    if refresh_ok:
        creds.refresh.side_effect = _refresh
    creds.to_json.return_value = json.dumps({"token": "t2", "refresh_token": "rt"})
    return creds


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------

class TestAuthenticate:
    def test_skips_flow_when_token_valid(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text("{}")
        client = GmailClient(credentials_path=tmp_path / "creds.json", token_path=token)
        with patch.object(client, "_load_token", return_value=_make_valid_creds()):
            client.authenticate()  # should not raise

    def test_refreshes_expired_token(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text("{}")
        creds = _make_expired_creds(refresh_ok=True)
        client = GmailClient(credentials_path=tmp_path / "creds.json", token_path=token)
        with patch.object(client, "_load_token", return_value=creds):
            with patch.object(client, "_save_token") as save:
                client.authenticate()
                save.assert_called_once_with(creds)

    def test_runs_full_flow_when_no_token(self, tmp_path):
        creds_file = tmp_path / "creds.json"
        creds_file.write_text("{}")
        client = GmailClient(credentials_path=creds_file, token_path=tmp_path / "token.json")
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = _make_valid_creds()
        with patch("app.mail.gmail_client.InstalledAppFlow.from_client_secrets_file",
                   return_value=mock_flow):
            with patch.object(client, "_save_token") as save:
                client.authenticate()
                mock_flow.run_local_server.assert_called_once_with(port=0)
                save.assert_called_once()

    def test_raises_when_credentials_missing(self, tmp_path):
        client = GmailClient(
            credentials_path=tmp_path / "missing.json",
            token_path=tmp_path / "token.json",
        )
        with pytest.raises(GmailAuthError, match="credentials.json not found"):
            client.authenticate()


# ---------------------------------------------------------------------------
# get_service()
# ---------------------------------------------------------------------------

class TestGetService:
    def test_returns_service_when_valid(self, tmp_path):
        client = GmailClient(credentials_path=tmp_path / "c.json", token_path=tmp_path / "t.json")
        creds = _make_valid_creds()
        with patch.object(client, "_load_token", return_value=creds):
            with patch("app.mail.gmail_client.build", return_value=MagicMock()) as build_mock:
                svc = client.get_service()
                build_mock.assert_called_once_with("gmail", "v1", credentials=creds)
                assert svc is build_mock.return_value

    def test_caches_service(self, tmp_path):
        client = GmailClient(credentials_path=tmp_path / "c.json", token_path=tmp_path / "t.json")
        creds = _make_valid_creds()
        with patch.object(client, "_load_token", return_value=creds):
            with patch("app.mail.gmail_client.build", return_value=MagicMock()) as build_mock:
                s1 = client.get_service()
                s2 = client.get_service()
                assert s1 is s2
                build_mock.assert_called_once()  # built only once

    def test_raises_when_not_authenticated(self, tmp_path):
        client = GmailClient(credentials_path=tmp_path / "c.json", token_path=tmp_path / "t.json")
        with patch.object(client, "_load_token", return_value=None):
            with pytest.raises(GmailAuthError, match="Not authenticated"):
                client.get_service()


# ---------------------------------------------------------------------------
# logout()
# ---------------------------------------------------------------------------

class TestLogout:
    def test_removes_token_file(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text("{}")
        client = GmailClient(credentials_path=tmp_path / "c.json", token_path=token)
        client.logout()
        assert not token.exists()

    def test_noop_when_no_token(self, tmp_path):
        client = GmailClient(
            credentials_path=tmp_path / "c.json",
            token_path=tmp_path / "no_token.json",
        )
        client.logout()  # should not raise

    def test_clears_cached_service(self, tmp_path):
        client = GmailClient(credentials_path=tmp_path / "c.json", token_path=tmp_path / "t.json")
        client._service = MagicMock()
        client.logout()
        assert client._service is None
