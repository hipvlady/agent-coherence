"""Tests for product catalog API."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import datetime


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def sample_product():
    from models.product import Product, ProductCategory, ProductStatus, ProductVariant
    product = Product(
        id=1, slug="widget-pro", title="Widget Pro", description="A great widget",
        category=ProductCategory.ELECTRONICS, status=ProductStatus.ACTIVE,
        created_at=datetime(2025, 1, 1), updated_at=datetime(2025, 1, 1),
    )
    product.variants = [
        ProductVariant(sku="WP-BLK", name="Black", price=Decimal("29.99"), stock_quantity=50),
        ProductVariant(sku="WP-WHT", name="White", price=Decimal("29.99"), stock_quantity=0),
    ]
    return product


def test_get_product_returns_variants(db, sample_product):
    from api.products import get_product
    db.query.return_value.filter.return_value.first.return_value = sample_product
    result = get_product({}, slug="widget-pro", db=db)
    assert "variants" in result.get("data", {})
    assert len(result["data"]["variants"]) == 2


def test_get_product_not_found(db):
    from api.products import get_product
    db.query.return_value.filter.return_value.first.return_value = None
    result = get_product({}, slug="nonexistent", db=db)
    assert result["status"] == 404


def test_create_product_requires_title(db):
    from api.products import create_product
    result = create_product({"description": "desc", "category": "electronics"}, db)
    assert "error" in result


def test_create_product_rejects_invalid_category(db):
    from api.products import create_product
    result = create_product({"title": "T", "description": "D", "category": "invalid"}, db)
    assert result.get("status") == 400


def test_search_requires_query(db):
    from api.products import search_products
    result = search_products({}, db)
    assert result.get("status") == 400


def test_product_base_price_uses_minimum(sample_product):
    from models.product import ProductVariant
    from decimal import Decimal
    sample_product.variants.append(
        ProductVariant(sku="WP-RED", name="Red", price=Decimal("19.99"), stock_quantity=10)
    )
    assert sample_product.base_price == Decimal("19.99")


def test_product_is_in_stock_checks_any_variant(sample_product):
    assert sample_product.is_in_stock is True
    for v in sample_product.variants:
        v.stock_quantity = 0
    assert sample_product.is_in_stock is False
