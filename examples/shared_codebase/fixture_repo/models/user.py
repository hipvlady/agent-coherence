"""User domain model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import re


EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 128


@dataclass
class UserAddress:
    street: str
    city: str
    country: str
    postal_code: str
    state: Optional[str] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.street.strip():
            errors.append("street is required")
        if not self.city.strip():
            errors.append("city is required")
        if len(self.postal_code) < 3:
            errors.append("postal_code too short")
        return errors


@dataclass
class UserPreferences:
    locale: str = "en-US"
    timezone: str = "UTC"
    email_notifications: bool = True
    marketing_emails: bool = False
    two_factor_enabled: bool = False


@dataclass
class User:
    id: int
    email: str
    username: str
    password_hash: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    is_admin: bool = False
    address: Optional[UserAddress] = None
    preferences: UserPreferences = field(default_factory=UserPreferences)
    _login_attempts: int = field(default=0, repr=False)

    @classmethod
    def create(cls, email: str, username: str, plain_password: str) -> "User":
        _validate_email(email)
        _validate_password(plain_password)
        now = datetime.utcnow()
        return cls(
            id=0,
            email=email.lower().strip(),
            username=username.strip(),
            password_hash=_hash_password(plain_password),
            created_at=now,
            updated_at=now,
        )

    def check_password(self, plain_password: str) -> bool:
        return self.password_hash == _hash_password(plain_password)

    def change_password(self, old_password: str, new_password: str) -> None:
        if not self.check_password(old_password):
            raise ValueError("current password incorrect")
        _validate_password(new_password)
        self.password_hash = _hash_password(new_password)
        self.updated_at = datetime.utcnow()

    def record_login_attempt(self, success: bool) -> None:
        if success:
            self._login_attempts = 0
        else:
            self._login_attempts += 1

    def is_locked_out(self) -> bool:
        return self._login_attempts >= 5

    def deactivate(self) -> None:
        self.is_active = False
        self.updated_at = datetime.utcnow()

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


def _validate_email(email: str) -> None:
    if not EMAIL_RE.match(email):
        raise ValueError(f"invalid email: {email!r}")


def _validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LEN:
        raise ValueError(f"password must be at least {PASSWORD_MIN_LEN} chars")
    if len(password) > PASSWORD_MAX_LEN:
        raise ValueError(f"password must be at most {PASSWORD_MAX_LEN} chars")


def _hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()
