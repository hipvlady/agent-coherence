"""Tests for order management."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import datetime


@pytest.fixture
def sample_order():
    from models.order import Order, OrderItem, OrderStatus, PaymentStatus
    items = [
        OrderItem(product_id=1, variant_sku="WP-BLK", product_title="Widget",
                  quantity=2, unit_price=Decimal("29.99"), tax_rate=Decimal("0.10")),
    ]
    return Order(
        id=1, user_id=42, status=OrderStatus.PENDING, payment_status=PaymentStatus.UNPAID,
        items=items, created_at=datetime(2025, 1, 1), updated_at=datetime(2025, 1, 1),
    )


def test_order_item_subtotal(sample_order):
    item = sample_order.items[0]
    assert item.subtotal == Decimal("59.98")


def test_order_item_tax(sample_order):
    item = sample_order.items[0]
    assert item.tax_amount == Decimal("5.998")


def test_order_grand_total(sample_order):
    assert sample_order.grand_total == pytest.approx(Decimal("65.978"), rel=Decimal("0.001"))


def test_order_confirm(sample_order):
    from models.order import OrderStatus
    sample_order.confirm()
    assert sample_order.status == OrderStatus.CONFIRMED


def test_order_cancel_pending(sample_order):
    from models.order import OrderStatus
    sample_order.cancel("customer request")
    assert sample_order.status == OrderStatus.CANCELLED
    assert sample_order.notes == "customer request"


def test_order_cancel_shipped_raises(sample_order):
    from models.order import OrderStatus
    sample_order.status = OrderStatus.SHIPPED
    with pytest.raises(ValueError, match="cancel"):
        sample_order.cancel()


def test_order_ship_requires_processing(sample_order):
    from models.order import OrderStatus
    with pytest.raises(ValueError):
        sample_order.ship("FedEx", "track123")
    sample_order.status = OrderStatus.PROCESSING
    sample_order.ship("FedEx", "track123")
    assert sample_order.status == OrderStatus.SHIPPED


def test_order_item_count(sample_order):
    assert sample_order.item_count() == 2
