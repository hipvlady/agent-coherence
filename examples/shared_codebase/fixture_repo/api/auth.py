"""Authentication and authorization API."""
from __future__ import annotations
from typing import Any, Optional
from datetime import datetime
import logging
import secrets

logger = logging.getLogger(__name__)

ROUTES = {
    "POST /auth/login": "login",
    "POST /auth/logout": "logout",
    "POST /auth/refresh": "refresh_token",
    "POST /auth/forgot-password": "forgot_password",
    "POST /auth/reset-password": "reset_password",
    "POST /auth/verify-email": "verify_email",
    "POST /auth/2fa/enable": "enable_2fa",
    "POST /auth/2fa/verify": "verify_2fa",
    "GET /auth/sessions": "list_sessions",
    "DELETE /auth/sessions/{id}": "revoke_session",
}

PASSWORD_RESET_TTL_MINUTES = 30
EMAIL_VERIFY_TTL_HOURS = 24


def login(request: dict, db: Any) -> dict:
    """Authenticate and create a session.

    Rate limited: 10 attempts per 15 minutes per IP.
    On 5th consecutive failure, account is locked.
    """
    email = request.get("email", "").lower().strip()
    password = request.get("password", "")
    ip = request.get("ip_address", "")
    user_agent = request.get("user_agent", "")

    if _is_rate_limited(ip, db):
        logger.warning("login rate limit exceeded: ip=%s", ip)
        return {"error": "too many requests", "status": 429}

    user = db.query("users").filter(email=email, is_active=True).first()
    if not user:
        _record_failed_attempt(ip, db)
        return {"error": "invalid credentials", "status": 401}

    if user.is_locked_out():
        return {"error": "account locked", "status": 423}

    if not user.check_password(password):
        user.record_login_attempt(success=False)
        _record_failed_attempt(ip, db)
        db.commit()
        return {"error": "invalid credentials", "status": 401}

    user.record_login_attempt(success=True)
    from models.session import Session, DeviceInfo
    device = DeviceInfo(user_agent=user_agent, ip_address=ip)
    session = Session.create(user.id, device=device)
    db.add(session)
    db.commit()
    logger.info("login success: user=%d ip=%s", user.id, ip)
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_in": 86400,
    }


def refresh_token(request: dict, db: Any) -> dict:
    """Exchange a valid refresh token for a new access token."""
    token = request.get("refresh_token", "")
    session = db.query("sessions").filter(refresh_token=token).first()
    if not session:
        return {"error": "invalid refresh token", "status": 401}
    try:
        new_access_token = session.refresh()
    except ValueError:
        return {"error": "refresh token expired", "status": 401}
    db.commit()
    return {"access_token": new_access_token, "expires_in": 86400}


def forgot_password(request: dict, db: Any) -> dict:
    """Send password reset email. Returns 200 even if email not found (avoid enumeration)."""
    email = request.get("email", "").lower().strip()
    user = db.query("users").filter(email=email, is_active=True).first()
    if user:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow()
        db.store("password_resets", {"token": token, "user_id": user.id,
                                      "expires_at": expires_at, "used": False})
        db.commit()
        logger.info("password reset requested for user=%d", user.id)
    return {"message": "if that email exists, a reset link was sent", "status": 200}


def _is_rate_limited(ip: str, db: Any) -> bool:
    from datetime import timedelta
    window_start = datetime.utcnow() - timedelta(minutes=15)
    attempts = db.query("login_attempts").filter(
        ip_address=ip, created_at__gte=window_start
    ).count()
    return attempts >= 10


def _record_failed_attempt(ip: str, db: Any) -> None:
    db.store("login_attempts", {"ip_address": ip, "created_at": datetime.utcnow()})
