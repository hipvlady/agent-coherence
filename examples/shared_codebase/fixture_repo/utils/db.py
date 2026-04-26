"""Database connection and query utilities."""
from __future__ import annotations
from typing import Any, Optional, TypeVar, Generic
from contextlib import contextmanager
import logging
import time

logger = logging.getLogger(__name__)

T = TypeVar("T")
QUERY_TIMEOUT_MS = 5000
MAX_RETRIES = 3
RETRY_BACKOFF_MS = 100


class QueryBuilder(Generic[T]):
    def __init__(self, table: str, db: Any) -> None:
        self._table = table
        self._db = db
        self._filters: list[dict] = []
        self._order_by: Optional[str] = None
        self._limit: Optional[int] = None
        self._offset: int = 0

    def filter(self, **kwargs) -> "QueryBuilder[T]":
        self._filters.append(kwargs)
        return self

    def filter_or(self, **kwargs) -> "QueryBuilder[T]":
        self._filters.append({"__or__": kwargs})
        return self

    def order_by(self, field: str) -> "QueryBuilder[T]":
        self._order_by = field
        return self

    def limit(self, n: int) -> "QueryBuilder[T]":
        self._limit = n
        return self

    def offset(self, n: int) -> "QueryBuilder[T]":
        self._offset = n
        return self

    def count(self) -> int:
        return self._db.execute_count(self._table, self._filters)

    def first(self) -> Optional[T]:
        results = self._db.execute_query(self._table, self._filters,
                                          order_by=self._order_by, limit=1, offset=0)
        return results[0] if results else None

    def all(self) -> list[T]:
        return self._db.execute_query(self._table, self._filters,
                                       order_by=self._order_by,
                                       limit=self._limit, offset=self._offset)

    def exists(self) -> bool:
        return self.count() > 0


class DatabaseConnection:
    def __init__(self, url: str, pool_size: int = 10, max_overflow: int = 5) -> None:
        self._url = url
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._connection = None

    def connect(self) -> None:
        logger.info("connecting to database: %s", self._url.split("@")[-1])
        # Implementation omitted — driver-specific

    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    def query(self, table: str) -> QueryBuilder:
        return QueryBuilder(table, self)

    def add(self, obj: Any) -> None:
        self._session.add(obj)

    def commit(self) -> None:
        for attempt in range(MAX_RETRIES):
            try:
                self._session.commit()
                return
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    self._session.rollback()
                    raise
                time.sleep(RETRY_BACKOFF_MS * (2 ** attempt) / 1000)

    def flush(self) -> None:
        self._session.flush()

    def store(self, table: str, data: dict) -> None:
        self._session.execute(f"INSERT INTO {table}", data)

    def full_text_search(self, table: str, query: str, limit: int = 20) -> list:
        return self._session.execute(f"SELECT * FROM {table} WHERE ...", {"q": query, "limit": limit})

    @contextmanager
    def transaction(self):
        try:
            yield self
            self.commit()
        except Exception:
            self._session.rollback()
            raise
