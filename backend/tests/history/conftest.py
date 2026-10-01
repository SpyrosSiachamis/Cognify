"""One store fixture, parametrized by implementation (the contract suite)."""

import os

import pytest

from app.seed import seed_store
from app.services.history import InMemoryHistory

STORES = [
    "memory",
    pytest.param(
        "postgres",
        marks=pytest.mark.skipif(
            not (os.environ.get("DATABASE_URL") and os.environ.get("STORAGE") == "postgres"),
            reason="Postgres store arrives at M5 (needs DATABASE_URL and STORAGE=postgres)",
        ),
    ),
]


@pytest.fixture(params=STORES)
def store(request):
    if request.param == "memory":
        fresh = InMemoryHistory()
    else:  # postgres: wire it here at M5
        raise NotImplementedError("arrives at M5")
    seed_store(fresh)
    return fresh
