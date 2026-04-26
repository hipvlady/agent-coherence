"""Input validation utilities."""
from __future__ import annotations
from typing import Any, Optional
from decimal import Decimal, InvalidOperation
import re
import logging

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")
PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SGD"}
MAX_STRING_LENGTH = 10_000
MIN_PASSWORD_ENTROPY_BITS = 28


class ValidationError(Exception):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class Validator:
    def __init__(self) -> None:
        self._errors: list[ValidationError] = []

    def require(self, value: Any, field: str) -> "Validator":
        if value is None or (isinstance(value, str) and not value.strip()):
            self._errors.append(ValidationError(field, "is required"))
        return self

    def email(self, value: str, field: str = "email") -> "Validator":
        if value and not EMAIL_RE.match(value):
            self._errors.append(ValidationError(field, f"invalid email format: {value!r}"))
        return self

    def phone(self, value: str, field: str = "phone") -> "Validator":
        if value and not PHONE_RE.match(value):
            self._errors.append(ValidationError(field, f"invalid phone format: {value!r}"))
        return self

    def slug(self, value: str, field: str = "slug") -> "Validator":
        if value and not SLUG_RE.match(value):
            self._errors.append(ValidationError(field, "must be lowercase alphanumeric with hyphens"))
        return self

    def url(self, value: str, field: str = "url") -> "Validator":
        if value and not URL_RE.match(value):
            self._errors.append(ValidationError(field, f"invalid URL: {value!r}"))
        return self

    def length(self, value: str, field: str, min_len: int = 0, max_len: int = MAX_STRING_LENGTH) -> "Validator":
        if value is not None:
            if len(value) < min_len:
                self._errors.append(ValidationError(field, f"too short (min {min_len} chars)"))
            if len(value) > max_len:
                self._errors.append(ValidationError(field, f"too long (max {max_len} chars)"))
        return self

    def currency(self, value: str, field: str = "currency") -> "Validator":
        if value and value.upper() not in SUPPORTED_CURRENCIES:
            self._errors.append(ValidationError(field, f"unsupported currency: {value!r}"))
        return self

    def amount(self, value: Any, field: str = "amount",
               min_value: Optional[Decimal] = None,
               max_value: Optional[Decimal] = None) -> "Validator":
        try:
            d = Decimal(str(value))
            if min_value is not None and d < min_value:
                self._errors.append(ValidationError(field, f"must be >= {min_value}"))
            if max_value is not None and d > max_value:
                self._errors.append(ValidationError(field, f"must be <= {max_value}"))
        except (InvalidOperation, TypeError):
            self._errors.append(ValidationError(field, f"invalid decimal: {value!r}"))
        return self

    def is_valid(self) -> bool:
        return len(self._errors) == 0

    def raise_if_invalid(self) -> None:
        if self._errors:
            raise self._errors[0]

    def to_dict(self) -> dict[str, str]:
        return {e.field: e.message for e in self._errors}
