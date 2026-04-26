"""Payment processing API endpoints."""
from __future__ import annotations
from typing import Any
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

ROUTES = {
    "POST /payments/charge": "charge_payment",
    "POST /payments/{id}/refund": "refund_payment",
    "GET /payments/{id}": "get_payment",
    "GET /payments/methods": "list_payment_methods",
    "POST /payments/methods": "add_payment_method",
    "DELETE /payments/methods/{id}": "remove_payment_method",
    "POST /payments/webhook/stripe": "stripe_webhook",
    "POST /payments/webhook/paypal": "paypal_webhook",
}


def charge_payment(request: dict, db: Any, gateway_client: Any) -> dict:
    """Charge a payment for an order.

    Body: order_id, payment_method_id, amount, currency
    Creates a transaction record and calls the payment gateway.
    """
    order_id = request.get("order_id")
    amount = Decimal(str(request.get("amount", "0")))
    currency = request.get("currency", "USD").upper()
    user_id = request["user_id"]

    order = db.query("orders").filter(id=order_id, user_id=user_id).first()
    if not order:
        return {"error": "order not found", "status": 404}
    if amount <= 0:
        return {"error": "amount must be positive", "status": 400}
    if amount > order.grand_total:
        return {"error": "amount exceeds order total", "status": 400}

    from models.payment import PaymentTransaction, PaymentMethod, PaymentGateway
    txn = PaymentTransaction.initiate(
        order_id=order_id, user_id=user_id, amount=amount,
        currency=currency, method=PaymentMethod.CARD, gateway=PaymentGateway.STRIPE,
    )
    db.add(txn)
    db.flush()

    try:
        gateway_response = gateway_client.charge(amount=amount, currency=currency,
                                                   metadata={"order_id": order_id})
        txn.mark_succeeded(gateway_response["id"])
        db.commit()
        logger.info("payment succeeded: txn=%s order=%d amount=%s", txn.id, order_id, amount)
        return {"data": {"transaction_id": txn.id, "status": "succeeded"}}
    except Exception as e:
        txn.mark_failed(str(e))
        db.commit()
        logger.error("payment failed: txn=%s error=%s", txn.id, e)
        return {"error": "payment failed", "detail": str(e), "status": 402}


def stripe_webhook(request: dict, db: Any) -> dict:
    """Handle Stripe webhook events.

    Verifies signature, processes payment_intent.succeeded and charge.refunded events.
    Idempotency: looks up transaction by gateway_transaction_id before processing.
    """
    payload = request.get("body", b"")
    signature = request.get("headers", {}).get("Stripe-Signature", "")
    webhook_secret = request.get("webhook_secret", "")
    if not _verify_stripe_signature(payload, signature, webhook_secret):
        logger.warning("stripe webhook signature mismatch")
        return {"error": "invalid signature", "status": 400}

    event = request.get("event", {})
    event_type = event.get("type")

    if event_type == "payment_intent.succeeded":
        gateway_id = event["data"]["object"]["id"]
        txn = db.query("payment_transactions").filter(gateway_transaction_id=gateway_id).first()
        if txn and txn.status.value != "succeeded":
            txn.mark_succeeded(gateway_id)
            db.commit()
    elif event_type == "charge.refunded":
        gateway_id = event["data"]["object"]["payment_intent"]
        refund_amount = Decimal(str(event["data"]["object"]["amount_refunded"])) / 100
        txn = db.query("payment_transactions").filter(gateway_transaction_id=gateway_id).first()
        if txn:
            try:
                txn.refund(refund_amount)
                db.commit()
            except ValueError as e:
                logger.error("refund error: %s", e)
    return {"status": 200}


def _verify_stripe_signature(payload: bytes, signature: str, secret: str) -> bool:
    import hmac, hashlib
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
