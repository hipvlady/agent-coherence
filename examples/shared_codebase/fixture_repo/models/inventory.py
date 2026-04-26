"""Inventory management model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MovementType(Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"
    DAMAGE = "damage"
    WRITE_OFF = "write_off"


@dataclass
class InventoryMovement:
    id: int
    sku: str
    warehouse_id: int
    movement_type: MovementType
    quantity_delta: int
    balance_after: int
    reference_id: Optional[str]
    created_at: datetime
    created_by: str
    notes: str = ""


@dataclass
class InventoryItem:
    sku: str
    warehouse_id: int
    quantity_on_hand: int
    quantity_reserved: int
    reorder_point: int
    reorder_quantity: int
    last_counted_at: Optional[datetime] = None
    movements: list[InventoryMovement] = field(default_factory=list)

    @property
    def quantity_available(self) -> int:
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def needs_reorder(self) -> bool:
        return self.quantity_available <= self.reorder_point

    def reserve(self, quantity: int, reference_id: str) -> None:
        if quantity > self.quantity_available:
            raise ValueError(
                f"insufficient stock: {self.quantity_available} available, {quantity} requested"
            )
        self.quantity_reserved += quantity
        logger.info("reserved %d units of %s (ref=%s)", quantity, self.sku, reference_id)

    def release_reservation(self, quantity: int, reference_id: str) -> None:
        self.quantity_reserved = max(0, self.quantity_reserved - quantity)
        logger.info("released reservation: %d units of %s (ref=%s)", quantity, self.sku, reference_id)

    def receive(self, quantity: int, reference_id: str, created_by: str) -> InventoryMovement:
        if quantity <= 0:
            raise ValueError("receive quantity must be positive")
        self.quantity_on_hand += quantity
        movement = InventoryMovement(
            id=0,
            sku=self.sku,
            warehouse_id=self.warehouse_id,
            movement_type=MovementType.PURCHASE,
            quantity_delta=quantity,
            balance_after=self.quantity_on_hand,
            reference_id=reference_id,
            created_at=datetime.utcnow(),
            created_by=created_by,
        )
        self.movements.append(movement)
        return movement

    def adjust(self, quantity_delta: int, reason: str, created_by: str) -> InventoryMovement:
        new_qty = self.quantity_on_hand + quantity_delta
        if new_qty < 0:
            raise ValueError(f"adjustment would result in negative stock: {new_qty}")
        self.quantity_on_hand = new_qty
        movement = InventoryMovement(
            id=0,
            sku=self.sku,
            warehouse_id=self.warehouse_id,
            movement_type=MovementType.ADJUSTMENT,
            quantity_delta=quantity_delta,
            balance_after=new_qty,
            reference_id=None,
            created_at=datetime.utcnow(),
            created_by=created_by,
            notes=reason,
        )
        self.movements.append(movement)
        return movement

    def cycle_count(self, actual_quantity: int, created_by: str) -> Optional[InventoryMovement]:
        delta = actual_quantity - self.quantity_on_hand
        if delta == 0:
            self.last_counted_at = datetime.utcnow()
            return None
        return self.adjust(delta, "cycle count adjustment", created_by)
