"""Search API endpoints."""
from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)

ROUTES = {
    "GET /search": "global_search",
    "GET /search/products": "search_products",
    "GET /search/users": "search_users",
    "POST /search/index": "trigger_reindex",
    "GET /search/suggest": "autocomplete",
}

MAX_RESULTS = 100
DEFAULT_RESULTS = 20


def global_search(request: dict, search_client: Any) -> dict:
    """Search across all entity types.

    Query: q (required), types (comma-sep: products,users,orders), limit, offset
    """
    query = request.get("q", "").strip()
    if len(query) < 2:
        return {"error": "query must be at least 2 characters", "status": 400}
    types = [t.strip() for t in request.get("types", "products").split(",")]
    valid_types = {"products", "users", "orders"}
    invalid = set(types) - valid_types
    if invalid:
        return {"error": f"unknown types: {invalid}", "status": 400}
    limit = min(MAX_RESULTS, int(request.get("limit", DEFAULT_RESULTS)))
    offset = int(request.get("offset", 0))

    results: dict[str, list] = {}
    for entity_type in types:
        hits = search_client.search(index=entity_type, query=query,
                                     limit=limit, offset=offset)
        results[entity_type] = [_format_hit(h, entity_type) for h in hits]
    total = sum(len(v) for v in results.values())
    logger.info("global search: %r types=%s hits=%d", query, types, total)
    return {"data": results, "total": total}


def autocomplete(request: dict, search_client: Any) -> dict:
    """Return autocomplete suggestions for partial queries.

    Query: q (min 2 chars), type (default: products), limit (max 10)
    """
    prefix = request.get("q", "").strip()
    if len(prefix) < 2:
        return {"suggestions": []}
    entity_type = request.get("type", "products")
    limit = min(10, int(request.get("limit", 5)))
    suggestions = search_client.suggest(index=entity_type, prefix=prefix, limit=limit)
    return {"suggestions": suggestions, "prefix": prefix}


def trigger_reindex(request: dict, search_client: Any, db: Any) -> dict:
    """Trigger full re-index of all entities (admin only, async operation).

    Returns a job_id for status polling.
    """
    if not request.get("is_admin"):
        return {"error": "admin access required", "status": 403}
    entity_type = request.get("type", "all")
    job_id = search_client.schedule_reindex(entity_type=entity_type)
    logger.info("reindex triggered: type=%s job_id=%s by admin=%d",
                entity_type, job_id, request.get("user_id"))
    return {"job_id": job_id, "status": "queued"}


def _format_hit(hit: dict, entity_type: str) -> dict:
    return {
        "id": hit.get("id"),
        "type": entity_type,
        "title": hit.get("title") or hit.get("name") or hit.get("email", ""),
        "score": round(hit.get("_score", 0.0), 3),
        "url": f"/{entity_type}/{hit.get('slug') or hit.get('id')}",
    }
