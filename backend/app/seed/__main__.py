"""Seed commands: python -m app.seed <show|load|reset-demo>."""

import argparse

from app.history import InMemoryHistory, get_store

from . import seed_store


def show() -> None:
    store = InMemoryHistory()
    seed_store(store)
    for student in store.list_students():
        print(f"{student.display_name} (seeded demo history)")
        for stat in store.strategy_stats(student.id):
            print(
                f"  {stat.gap_type:12} {stat.method:22} "
                f"{stat.independent_successes}/{stat.uses}  last success: {stat.last_success_at:%Y-%m-%d}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.seed")
    parser.add_argument(
        "command",
        choices=["show", "load", "reset-demo"],
        help=(
            "show: print the strategy stats from a fresh in-memory store. "
            "load: load the seed into the configured store (meant for Postgres; "
            "with STORAGE=memory it only fills this short-lived process, because the "
            "memory store lives inside the server). "
            "reset-demo: call reset_demo() on the configured store (same memory caveat)."
        ),
    )
    command = parser.parse_args().command
    if command == "show":
        show()
    elif command == "load":
        seed_store(get_store())
        print("Seed loaded into the configured store.")
    else:
        get_store().reset_demo()
        print("Demo reset.")


main()
