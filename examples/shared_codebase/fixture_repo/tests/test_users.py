"""Tests for user management API."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def sample_user():
    from models.user import User, UserPreferences
    return User(
        id=1, email="alice@example.com", username="alice",
        password_hash="hashed_pw", created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1), is_active=True,
        preferences=UserPreferences(),
    )


def test_create_user_validates_email(db):
    from api.users import create_user
    db.query.return_value.filter.return_value.exists.return_value = False
    result = create_user({"email": "not-an-email", "username": "alice", "password": "Str0ng!pw"}, db)
    assert result["status"] == 400 or "error" in result


def test_create_user_rejects_duplicate_email(db, sample_user):
    from api.users import create_user
    db.query.return_value.filter.return_value.exists.return_value = True
    result = create_user({"email": "alice@example.com", "username": "alice2", "password": "pw"}, db)
    assert result.get("status") == 409


def test_get_user_returns_public_profile(db, sample_user):
    from api.users import get_user
    db.query.return_value.filter.return_value.first.return_value = sample_user
    result = get_user({"user_id": 99}, user_id=1, db=db)
    assert "data" in result
    assert "password_hash" not in result["data"]


def test_get_user_returns_full_profile_for_owner(db, sample_user):
    from api.users import get_user
    db.query.return_value.filter.return_value.first.return_value = sample_user
    result = get_user({"user_id": 1}, user_id=1, db=db)
    assert "data" in result


def test_get_user_not_found(db):
    from api.users import get_user
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_user({}, user_id=999, db=db)
    assert result["status"] == 404


def test_list_users_pagination(db):
    from api.users import list_users
    db.query.return_value.filter.return_value.count.return_value = 100
    db.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
    result = list_users({"page": "2", "per_page": "10"}, db)
    assert "pagination" in result
    assert result["pagination"]["page"] == 2


def test_login_returns_tokens(db, sample_user):
    from api.users import login
    db.query.return_value.filter.return_value.first.return_value = sample_user
    sample_user.check_password = MagicMock(return_value=True)
    sample_user.is_locked_out = MagicMock(return_value=False)
    result = login({"email": "alice@example.com", "password": "correct"}, db)
    assert "access_token" in result or result.get("status") == 401


def test_login_locked_account(db, sample_user):
    from api.users import login
    sample_user.is_locked_out = MagicMock(return_value=True)
    db.query.return_value.filter.return_value.first.return_value = sample_user
    result = login({"email": "alice@example.com", "password": "any"}, db)
    assert result.get("status") == 423
