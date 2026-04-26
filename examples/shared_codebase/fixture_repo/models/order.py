"""Order domain model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from enum import Enum


class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    PARTIAL = "partial"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass
class OrderItem:
    product_id: int
    variant_sku: str
    product_title: str
    quantity: int
    unit_price: Decimal
    tax_rate: Decimal = Decimal("0.00")
    discount: Decimal = Decimal("0.00")

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def tax_amount(self) -> Decimal:
        return self.subtotal * self.tax_rate

    @property
    def discount_amount(self) -> Decimal:
        return self.subtotal * self.discount

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax_amount - self.discount_amount


@dataclass
class ShippingInfo:
    carrier: str
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    shipped_at: Optional[datetime] = None


@dataclass
class Order:
    id: int
    user_id: int
    status: OrderStatus
    payment_status: PaymentStatus
    items: list[OrderItem]
    created_at: datetime
    updated_at: datetime
    shipping_address: dict = field(default_factory=dict)
    shipping_info: Optional[ShippingInfo] = None
    notes: str = ""

    @property
    def subtotal(self) -> Decimal:
        return sum(item.subtotal for item in self.items)

    @property
    def tax_total(self) -> Decimal:
        return sum(item.tax_amount for item in self.items)

    @property
    def discount_total(self) -> Decimal:
        return sum(item.discount_amount for item in self.items)

    @property
    def grand_total(self) -> Decimal:
        return sum(item.total for item in self.items)

    def confirm(self) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"cannot confirm order in {self.status.value} state")
        self.status = OrderStatus.CONFIRMED
        self.updated_at = datetime.utcnow()

    def cancel(self, reason: str = "") -> None:
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise ValueError("cannot cancel shipped or delivered order")
        self.status = OrderStatus.CANCELLED
        self.notes = reason
        self.updated_at = datetime.utcnow()

    def ship(self, carrier: str, tracking: str) -> None:
        if self.status != OrderStatus.PROCESSING:
            raise ValueError("order must be processing before shipping")
        self.shipping_info = ShippingInfo(carrier=carrier, tracking_number=tracking,
                                          shipped_at=datetime.utcnow())
        self.status = OrderStatus.SHIPPED
        self.updated_at = datetime.utcnow()

    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)
