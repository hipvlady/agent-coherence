"""Distributed cache utilities (Redis-backed)."""
from __future__ import annotations
from typing import Any, Optional, Callable, TypeVar
from functools import wraps
import json
import logging
import time

logger = logging.getLogger(__name__)

T = TypeVar("T")
DEFAULT_TTL = 300
CACHE_VERSION = "v1"


class CacheKey:
    def __init__(self, namespace: str, *parts: Any) -> None:
        self._parts = (CACHE_VERSION, namespace, *parts)

    def __str__(self) -> str:
        return ":".join(str(p) for p in self._parts)

    def pattern(self) -> str:
        return f"{CACHE_VERSION}:{self._parts[1]}:*"


class RedisCache:
    def __init__(self, url: str, default_ttl: int = DEFAULT_TTL) -> None:
        self._url = url
        self._default_ttl = default_ttl
        self._client = None
        self._hits = 0
        self._misses = 0

    def connect(self) -> None:
        logger.info("connecting to Redis: %s", self._url)

    def get(self, key: CacheKey, default: Any = None) -> Any:
        raw = self._client.get(str(key))
        if raw is None:
            self._misses += 1
            return default
        self._hits += 1
        return json.loads(raw)

    def set(self, key: CacheKey, value: Any, ttl: Optional[int] = None) -> None:
        self._client.setex(str(key), ttl or self._default_ttl, json.dumps(value))

    def delete(self, key: CacheKey) -> bool:
        return bool(self._client.delete(str(key)))

    def invalidate_namespace(self, namespace: str) -> int:
        pattern = f"{CACHE_VERSION}:{namespace}:*"
        keys = self._client.scan_iter(pattern)
        if not keys:
            return 0
        return self._client.delete(*keys)

    def get_or_set(self, key: CacheKey, factory: Callable[[], T], ttl: Optional[int] = None) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl)
        return value

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "hit_rate": self.hit_rate}


def cached(namespace: str, ttl: int = DEFAULT_TTL, key_fn: Optional[Callable] = None):
    """Decorator to cache function results. Uses function args as cache key by default."""
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, cache: RedisCache, **kwargs) -> T:
            cache_key = key_fn(*args, **kwargs) if key_fn else CacheKey(namespace, *args)
            cached_val = cache.get(cache_key)
            if cached_val is not None:
                return cached_val
            result = fn(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator
