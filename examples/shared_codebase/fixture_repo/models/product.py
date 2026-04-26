"""Product domain model."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from enum import Enum


class ProductStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    OUT_OF_STOCK = "out_of_stock"


class ProductCategory(Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    FOOD = "food"
    BOOKS = "books"
    HOME = "home"
    OTHER = "other"


@dataclass
class ProductVariant:
    sku: str
    name: str
    price: Decimal
    stock_quantity: int
    weight_kg: Optional[float] = None
    attributes: dict = field(default_factory=dict)

    def is_available(self) -> bool:
        return self.stock_quantity > 0

    def reserve(self, quantity: int) -> None:
        if quantity > self.stock_quantity:
            raise ValueError(f"only {self.stock_quantity} units available, requested {quantity}")
        self.stock_quantity -= quantity

    def restock(self, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("restock quantity must be positive")
        self.stock_quantity += quantity


@dataclass
class ProductImage:
    url: str
    alt_text: str
    sort_order: int = 0
    is_primary: bool = False


@dataclass
class Product:
    id: int
    slug: str
    title: str
    description: str
    category: ProductCategory
    status: ProductStatus
    created_at: datetime
    updated_at: datetime
    brand: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    variants: list[ProductVariant] = field(default_factory=list)
    images: list[ProductImage] = field(default_factory=list)
    tax_rate: Decimal = Decimal("0.00")

    @property
    def base_price(self) -> Optional[Decimal]:
        if not self.variants:
            return None
        return min(v.price for v in self.variants)

    @property
    def is_in_stock(self) -> bool:
        return any(v.is_available() for v in self.variants)

    def get_variant(self, sku: str) -> Optional[ProductVariant]:
        return next((v for v in self.variants if v.sku == sku), None)

    def add_variant(self, variant: ProductVariant) -> None:
        if self.get_variant(variant.sku):
            raise ValueError(f"variant {variant.sku!r} already exists")
        self.variants.append(variant)

    def price_with_tax(self, variant_sku: str) -> Decimal:
        variant = self.get_variant(variant_sku)
        if variant is None:
            raise KeyError(f"variant {variant_sku!r} not found")
        return variant.price * (1 + self.tax_rate)

    def publish(self) -> None:
        if not self.variants:
            raise ValueError("cannot publish product with no variants")
        self.status = ProductStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def discontinue(self) -> None:
        self.status = ProductStatus.DISCONTINUED
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "category": self.category.value,
            "status": self.status.value,
            "base_price": str(self.base_price) if self.base_price else None,
            "is_in_stock": self.is_in_stock,
            "tag_count": len(self.tags),
        }
