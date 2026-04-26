"""User session model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib


SESSION_TTL_HOURS = 24
REFRESH_TOKEN_TTL_DAYS = 30
MAX_SESSIONS_PER_USER = 5


@dataclass
class DeviceInfo:
    user_agent: str
    ip_address: str
    device_type: str = "unknown"
    browser: str = "unknown"
    os: str = "unknown"

    def fingerprint(self) -> str:
        raw = f"{self.user_agent}:{self.ip_address}"
        return hashlib.md5(raw.encode()).hexdigest()


@dataclass
class Session:
    id: str
    user_id: int
    access_token: str
    refresh_token: str
    created_at: datetime
    expires_at: datetime
    refresh_expires_at: datetime
    device: Optional[DeviceInfo] = None
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    revoked_reason: str = ""
    last_used_at: Optional[datetime] = None

    @classmethod
    def create(cls, user_id: int, device: Optional[DeviceInfo] = None) -> "Session":
        now = datetime.utcnow()
        return cls(
            id=secrets.token_urlsafe(24),
            user_id=user_id,
            access_token=secrets.token_urlsafe(32),
            refresh_token=secrets.token_urlsafe(48),
            created_at=now,
            expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
            refresh_expires_at=now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
            device=device,
            last_used_at=now,
        )

    def is_valid(self) -> bool:
        return not self.revoked and datetime.utcnow() < self.expires_at

    def is_refresh_valid(self) -> bool:
        return not self.revoked and datetime.utcnow() < self.refresh_expires_at

    def refresh(self) -> str:
        if not self.is_refresh_valid():
            raise ValueError("refresh token expired or session revoked")
        self.access_token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        self.expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
        self.last_used_at = now
        return self.access_token

    def revoke(self, reason: str = "") -> None:
        self.revoked = True
        self.revoked_at = datetime.utcnow()
        self.revoked_reason = reason

    def touch(self) -> None:
        self.last_used_at = datetime.utcnow()
