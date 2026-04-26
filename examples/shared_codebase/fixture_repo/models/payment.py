"""Payment domain model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from enum import Enum
import secrets


class PaymentMethod(Enum):
    CARD = "card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    CRYPTO = "crypto"
    WALLET = "wallet"


class PaymentGateway(Enum):
    STRIPE = "stripe"
    PAYPAL = "paypal"
    ADYEN = "adyen"
    SQUARE = "square"


class TransactionStatus(Enum):
    INITIATED = "initiated"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass
class CardInfo:
    last4: str
    brand: str
    exp_month: int
    exp_year: int
    cardholder_name: str
    fingerprint: str

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.utcnow()
        return (self.exp_year, self.exp_month) < (now.year, now.month)


@dataclass
class PaymentTransaction:
    id: str
    order_id: int
    user_id: int
    amount: Decimal
    currency: str
    method: PaymentMethod
    gateway: PaymentGateway
    status: TransactionStatus
    created_at: datetime
    updated_at: datetime
    gateway_transaction_id: Optional[str] = None
    failure_reason: Optional[str] = None
    refund_amount: Decimal = Decimal("0.00")
    metadata: dict = field(default_factory=dict)

    @classmethod
    def initiate(cls, order_id: int, user_id: int, amount: Decimal,
                 currency: str, method: PaymentMethod, gateway: PaymentGateway) -> "PaymentTransaction":
        now = datetime.utcnow()
        return cls(
            id=secrets.token_urlsafe(16),
            order_id=order_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            method=method,
            gateway=gateway,
            status=TransactionStatus.INITIATED,
            created_at=now,
            updated_at=now,
        )

    def mark_succeeded(self, gateway_id: str) -> None:
        self.gateway_transaction_id = gateway_id
        self.status = TransactionStatus.SUCCEEDED
        self.updated_at = datetime.utcnow()

    def mark_failed(self, reason: str) -> None:
        self.failure_reason = reason
        self.status = TransactionStatus.FAILED
        self.updated_at = datetime.utcnow()

    def refund(self, amount: Optional[Decimal] = None) -> None:
        if self.status != TransactionStatus.SUCCEEDED:
            raise ValueError("can only refund succeeded transaction")
        refund_amount = amount or self.amount
        if refund_amount > self.amount:
            raise ValueError("refund exceeds original amount")
        self.refund_amount = refund_amount
        self.status = TransactionStatus.REFUNDED
        self.updated_at = datetime.utcnow()

    @property
    def net_amount(self) -> Decimal:
        return self.amount - self.refund_amount
