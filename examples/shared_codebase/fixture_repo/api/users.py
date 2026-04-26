"""User management API endpoints."""
from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)

# Endpoint definitions (framework-agnostic pseudocode)

ROUTES = {
    "GET /users": "list_users",
    "POST /users": "create_user",
    "GET /users/{id}": "get_user",
    "PUT /users/{id}": "update_user",
    "DELETE /users/{id}": "delete_user",
    "POST /users/{id}/deactivate": "deactivate_user",
    "GET /users/{id}/orders": "get_user_orders",
    "PUT /users/{id}/password": "change_password",
    "POST /users/auth/login": "login",
    "POST /users/auth/logout": "logout",
    "POST /users/auth/refresh": "refresh_token",
}


def list_users(request: dict, db: Any) -> dict:
    """List users with pagination and filtering.

    Query params: page, per_page (max 100), active, role, search
    Requires: admin role
    """
    page = max(1, int(request.get("page", 1)))
    per_page = min(100, max(1, int(request.get("per_page", 20))))
    search = request.get("search", "").strip()
    active_filter = request.get("active")
    offset = (page - 1) * per_page

    query = db.query("users")
    if search:
        query = query.filter_or(email__icontains=search, username__icontains=search)
    if active_filter is not None:
        query = query.filter(is_active=bool(active_filter))

    total = query.count()
    users = query.offset(offset).limit(per_page).all()
    return {
        "data": [u.to_public_dict() for u in users],
        "pagination": {"page": page, "per_page": per_page, "total": total},
    }


def create_user(request: dict, db: Any) -> dict:
    """Register a new user.

    Body: email, username, password
    Rate limited: 10 per hour per IP
    """
    email = request.get("email", "").strip().lower()
    username = request.get("username", "").strip()
    password = request.get("password", "")
    if not email or not username or not password:
        return {"error": "email, username, and password are required", "status": 400}
    if db.query("users").filter(email=email).exists():
        return {"error": "email already registered", "status": 409}
    if db.query("users").filter(username=username).exists():
        return {"error": "username taken", "status": 409}
    from models.user import User
    user = User.create(email=email, username=username, plain_password=password)
    db.add(user)
    db.commit()
    logger.info("new user registered: %s", email)
    return {"data": user.to_public_dict(), "status": 201}


def get_user(request: dict, user_id: int, db: Any) -> dict:
    """Get a user by ID. Returns public profile unless requesting own account or admin."""
    user = db.query("users").filter(id=user_id).first()
    if not user:
        return {"error": "user not found", "status": 404}
    requester_id = request.get("user_id")
    is_admin = request.get("is_admin", False)
    if is_admin or requester_id == user_id:
        return {"data": user.to_dict()}
    return {"data": user.to_public_dict()}


def update_user(request: dict, user_id: int, db: Any) -> dict:
    """Update user profile fields. Only allowed for own account or admin."""
    user = db.query("users").filter(id=user_id).first()
    if not user:
        return {"error": "user not found", "status": 404}
    allowed_fields = {"username", "preferences", "address"}
    updates = {k: v for k, v in request.items() if k in allowed_fields}
    for field_name, value in updates.items():
        setattr(user, field_name, value)
    db.commit()
    return {"data": user.to_public_dict()}


def login(request: dict, db: Any) -> dict:
    """Authenticate user and return session tokens.

    Body: email, password
    Returns: access_token, refresh_token, expires_in
    """
    email = request.get("email", "").lower().strip()
    password = request.get("password", "")
    user = db.query("users").filter(email=email).first()
    if not user or not user.is_active:
        return {"error": "invalid credentials", "status": 401}
    if user.is_locked_out():
        return {"error": "account locked due to too many failed attempts", "status": 423}
    if not user.check_password(password):
        user.record_login_attempt(success=False)
        db.commit()
        return {"error": "invalid credentials", "status": 401}
    user.record_login_attempt(success=True)
    db.commit()
    from models.session import Session
    session = Session.create(user.id)
    db.add(session)
    db.commit()
    logger.info("user logged in: %s", email)
    return {"access_token": session.access_token, "refresh_token": session.refresh_token}
