"""Tests for authentication utilities."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


def test_extract_token_from_bearer_header():
    from utils.auth import extract_token
    headers = {"Authorization": "Bearer my-token-123"}
    assert extract_token(headers) == "my-token-123"


def test_extract_token_missing_header():
    from utils.auth import extract_token
    assert extract_token({}) is None


def test_extract_token_wrong_scheme():
    from utils.auth import extract_token
    assert extract_token({"Authorization": "Basic abc123"}) is None


def test_verify_token_raises_on_invalid(monkeypatch):
    from utils.auth import verify_token, AuthError
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(AuthError):
        verify_token("bad-token", db)


def test_verify_token_raises_on_expired(monkeypatch):
    from utils.auth import verify_token, AuthError
    db = MagicMock()
    session = MagicMock()
    session.is_valid.return_value = False
    db.query.return_value.filter.return_value.first.return_value = session
    with pytest.raises(AuthError, match="expired"):
        verify_token("expired-token", db)


def test_verify_token_success():
    from utils.auth import verify_token
    db = MagicMock()
    session = MagicMock()
    session.is_valid.return_value = True
    session.user_id = 42
    session.id = "sess-1"
    db.query.return_value.filter.return_value.first.return_value = session
    ctx = verify_token("valid-token", db)
    assert ctx["user_id"] == 42


def test_admin_has_all_permissions():
    from utils.auth import ROLE_PERMISSIONS, PERMISSIONS, ROLE_ADMIN
    admin_perms = ROLE_PERMISSIONS[ROLE_ADMIN]
    assert set(PERMISSIONS.keys()).issubset(admin_perms)


def test_user_cannot_moderate_reviews():
    from utils.auth import ROLE_PERMISSIONS, ROLE_USER
    user_perms = ROLE_PERMISSIONS[ROLE_USER]
    assert "reviews:moderate" not in user_perms
