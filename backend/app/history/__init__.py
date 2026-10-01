"""History: the only door to storage. Pick the store with STORAGE (memory by default)."""

import os
from functools import lru_cache

from .interface import HistoryStore
from .memory import InMemoryHistory


@lru_cache
def get_store() -> HistoryStore:
    storage = os.environ.get("STORAGE", "memory")
    if storage == "memory":
        return InMemoryHistory()
    if storage == "postgres":
        raise NotImplementedError("arrives at M5")
    raise ValueError(f"unknown STORAGE {storage!r} (use memory or postgres)")


__all__ = ["HistoryStore", "InMemoryHistory", "get_store"]
