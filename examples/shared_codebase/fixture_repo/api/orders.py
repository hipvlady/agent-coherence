"""Order management API endpoints."""
from __future__ import annotations
from typing import Any
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

ROUTES = {
    "GET /orders": "list_orders",
    "POST /orders": "create_order",
    "GET /orders/{id}": "get_order",
    "POST /orders/{id}/confirm": "confirm_order",
    "POST /orders/{id}/cancel": "cancel_order",
    "POST /orders/{id}/ship": "ship_order",
    "GET /orders/{id}/items": "list_order_items",
    "POST /orders/{id}/refund": "request_refund",
}


def create_order(request: dict, db: Any) -> dict:
    """Create a new order from cart items.

    Body: items=[{product_id, variant_sku, quantity}], shipping_address
    Validates stock availability before creating.
    """
    items_data = request.get("items", [])
    if not items_data:
        return {"error": "order must have at least one item", "status": 400}
    shipping_address = request.get("shipping_address")
    if not shipping_address:
        return {"error": "shipping address is required", "status": 400}
    user_id = request["user_id"]

    order_items = []
    for item_data in items_data:
        product = db.query("products").filter(id=item_data["product_id"]).first()
        if not product:
            return {"error": f"product {item_data['product_id']} not found", "status": 404}
        variant = product.get_variant(item_data["variant_sku"])
        if not variant:
            return {"error": f"variant {item_data['variant_sku']!r} not found", "status": 404}
        if variant.stock_quantity < item_data["quantity"]:
            return {"error": f"insufficient stock for {item_data['variant_sku']!r}", "status": 409}
        from models.order import OrderItem
        order_items.append(OrderItem(
            product_id=product.id, variant_sku=variant.sku,
            product_title=product.title, quantity=item_data["quantity"],
            unit_price=variant.price, tax_rate=product.tax_rate,
        ))

    from models.order import Order, OrderStatus, PaymentStatus
    from datetime import datetime
    now = datetime.utcnow()
    order = Order(
        id=0, user_id=user_id, status=OrderStatus.PENDING,
        payment_status=PaymentStatus.UNPAID, items=order_items,
        created_at=now, updated_at=now, shipping_address=shipping_address,
    )
    db.add(order)
    db.commit()
    logger.info("order created: user=%d total=%s", user_id, str(order.grand_total))
    return {"data": {"id": order.id, "total": str(order.grand_total)}, "status": 201}


def cancel_order(request: dict, order_id: int, db: Any) -> dict:
    """Cancel an order. Only allowed for PENDING or CONFIRMED orders."""
    order = db.query("orders").filter(id=order_id).first()
    if not order:
        return {"error": "order not found", "status": 404}
    if order.user_id != request.get("user_id") and not request.get("is_admin"):
        return {"error": "forbidden", "status": 403}
    reason = request.get("reason", "")
    try:
        order.cancel(reason)
    except ValueError as e:
        return {"error": str(e), "status": 400}
    db.commit()
    return {"data": {"id": order.id, "status": order.status.value}}


def ship_order(request: dict, order_id: int, db: Any) -> dict:
    """Mark order as shipped (admin/fulfillment only).

    Body: carrier, tracking_number
    """
    order = db.query("orders").filter(id=order_id).first()
    if not order:
        return {"error": "order not found", "status": 404}
    carrier = request.get("carrier", "").strip()
    tracking = request.get("tracking_number", "").strip()
    if not carrier or not tracking:
        return {"error": "carrier and tracking_number are required", "status": 400}
    try:
        order.ship(carrier, tracking)
    except ValueError as e:
        return {"error": str(e), "status": 400}
    db.commit()
    return {"data": {"id": order.id, "status": order.status.value, "tracking": tracking}}
