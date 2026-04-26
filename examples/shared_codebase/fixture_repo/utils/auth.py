"""Authentication middleware and authorization utilities."""
from __future__ import annotations
from typing import Any, Callable, Optional
from functools import wraps
import logging
import time

logger = logging.getLogger(__name__)

TOKEN_HEADER = "Authorization"
TOKEN_PREFIX = "Bearer "
ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"
ROLE_USER = "user"


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class Permission:
    def __init__(self, resource: str, action: str) -> None:
        self.resource = resource
        self.action = action

    def __repr__(self) -> str:
        return f"Permission({self.resource}:{self.action})"


PERMISSIONS = {
    "users:read": Permission("users", "read"),
    "users:write": Permission("users", "write"),
    "users:admin": Permission("users", "admin"),
    "products:read": Permission("products", "read"),
    "products:write": Permission("products", "write"),
    "orders:read": Permission("orders", "read"),
    "orders:write": Permission("orders", "write"),
    "orders:admin": Permission("orders", "admin"),
    "payments:read": Permission("payments", "read"),
    "payments:write": Permission("payments", "write"),
    "reviews:read": Permission("reviews", "read"),
    "reviews:moderate": Permission("reviews", "moderate"),
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_USER: {"users:read", "products:read", "orders:read", "reviews:read"},
    ROLE_MODERATOR: {"users:read", "products:read", "orders:read", "reviews:read",
                     "reviews:moderate"},
    ROLE_ADMIN: set(PERMISSIONS.keys()),
}


def extract_token(headers: dict) -> Optional[str]:
    auth = headers.get(TOKEN_HEADER, "")
    if not auth.startswith(TOKEN_PREFIX):
        return None
    return auth[len(TOKEN_PREFIX):]


def verify_token(token: str, db: Any) -> dict:
    session = db.query("sessions").filter(access_token=token).first()
    if not session:
        raise AuthError("invalid or expired token")
    if not session.is_valid():
        raise AuthError("token expired")
    session.touch()
    return {"user_id": session.user_id, "session_id": session.id}


def get_user_permissions(user_id: int, db: Any) -> set[str]:
    user = db.query("users").filter(id=user_id).first()
    if not user:
        return set()
    role = ROLE_ADMIN if user.is_admin else ROLE_USER
    return ROLE_PERMISSIONS.get(role, set())


def require_permission(permission: str):
    """Decorator to enforce a specific permission on an endpoint handler."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(request: dict, *args, db: Any, **kwargs):
            token = extract_token(request.get("headers", {}))
            if not token:
                return {"error": "authentication required", "status": 401}
            try:
                ctx = verify_token(token, db)
            except AuthError as e:
                return {"error": str(e), "status": e.status_code}
            perms = get_user_permissions(ctx["user_id"], db)
            if permission not in perms:
                return {"error": "insufficient permissions", "status": 403}
            return fn({**request, **ctx}, *args, db=db, **kwargs)
        return wrapper
    return decorator


def require_admin(fn: Callable) -> Callable:
    return require_permission("users:admin")(fn)
