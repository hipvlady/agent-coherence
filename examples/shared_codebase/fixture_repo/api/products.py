"""Product catalog API endpoints."""
from __future__ import annotations
from typing import Any
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

ROUTES = {
    "GET /products": "list_products",
    "POST /products": "create_product",
    "GET /products/{slug}": "get_product",
    "PUT /products/{id}": "update_product",
    "DELETE /products/{id}": "archive_product",
    "POST /products/{id}/publish": "publish_product",
    "GET /products/{id}/variants": "list_variants",
    "POST /products/{id}/variants": "add_variant",
    "PUT /products/{id}/variants/{sku}": "update_variant",
    "GET /products/search": "search_products",
}


def list_products(request: dict, db: Any) -> dict:
    """List active products with pagination, category, and price filters.

    Query: page, per_page, category, min_price, max_price, in_stock, tag
    """
    page = max(1, int(request.get("page", 1)))
    per_page = min(50, int(request.get("per_page", 20)))
    category = request.get("category")
    min_price = request.get("min_price")
    max_price = request.get("max_price")
    in_stock = request.get("in_stock")
    offset = (page - 1) * per_page

    query = db.query("products").filter(status="active")
    if category:
        query = query.filter(category=category)
    if min_price is not None:
        query = query.filter(base_price__gte=Decimal(str(min_price)))
    if max_price is not None:
        query = query.filter(base_price__lte=Decimal(str(max_price)))
    if in_stock:
        query = query.filter(is_in_stock=True)

    total = query.count()
    products = query.offset(offset).limit(per_page).all()
    return {
        "data": [p.to_dict() for p in products],
        "pagination": {"page": page, "per_page": per_page, "total": total},
    }


def get_product(request: dict, slug: str, db: Any) -> dict:
    """Get product details including all variants and images."""
    product = db.query("products").filter(slug=slug).first()
    if not product:
        return {"error": "product not found", "status": 404}
    return {"data": {
        **product.to_dict(),
        "variants": [{"sku": v.sku, "name": v.name, "price": str(v.price),
                       "available": v.is_available()} for v in product.variants],
        "images": [{"url": i.url, "alt": i.alt_text} for i in product.images],
    }}


def create_product(request: dict, db: Any) -> dict:
    """Create a new product (admin only).

    Body: title, description, category, brand, tags
    """
    required = ["title", "description", "category"]
    for field in required:
        if not request.get(field):
            return {"error": f"{field} is required", "status": 400}
    from models.product import Product, ProductCategory, ProductStatus
    from datetime import datetime
    now = datetime.utcnow()
    try:
        category = ProductCategory(request["category"])
    except ValueError:
        return {"error": f"invalid category: {request['category']!r}", "status": 400}
    product = Product(
        id=0, slug="", title=request["title"], description=request["description"],
        category=category, status=ProductStatus.DRAFT, created_at=now, updated_at=now,
        brand=request.get("brand"), tags=request.get("tags", []),
    )
    db.add(product)
    db.commit()
    return {"data": product.to_dict(), "status": 201}


def search_products(request: dict, db: Any) -> dict:
    """Full-text search across product titles, descriptions, and tags.

    Query: q (required), limit (max 100), category, in_stock
    """
    query_text = request.get("q", "").strip()
    if not query_text:
        return {"error": "q parameter is required", "status": 400}
    limit = min(100, int(request.get("limit", 20)))
    results = db.full_text_search("products", query_text, limit=limit)
    logger.info("product search: %r → %d results", query_text, len(results))
    return {"data": [p.to_dict() for p in results], "total": len(results)}
