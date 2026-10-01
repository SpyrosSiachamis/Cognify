"""Seeded demo history for Maria and Nikos."""

import os
from datetime import datetime

from app.history import HistoryStore, get_store

from .data import build_seed


def seed_store(store: HistoryStore, now: datetime | None = None) -> None:
    seed = build_seed(now)
    store.load_seed(seed.students, seed.concepts, seed.outcomes, seed.concept_states)


def autoseed() -> bool:
    """At startup: load the seed into the memory store unless AUTOSEED=false."""
    if os.environ.get("STORAGE", "memory") != "memory":
        return False
    if os.environ.get("AUTOSEED", "true").lower() != "true":
        return False
    seed_store(get_store())
    return True
