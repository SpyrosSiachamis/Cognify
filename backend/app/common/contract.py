"""Shared helpers for the API schemas: the strict config with OpenAPI examples, and example IDs."""

from typing import Any

from pydantic import ConfigDict

MARIA = "16e82ef2-adee-4671-8393-c6b50ac91672"
SESSION = "d96e9546-b0bf-43a7-acdc-42f43ae8adac"
CONCEPT = "44d54897-9ec4-45b9-8da1-d4ea95697d1d"
PROBLEM = (
    "A ball is thrown vertically upward with an initial velocity of 20 m/s. "
    "How high does it go before it starts to fall? (Use g = 9.8 m/s^2)"
)


def contract(*examples: dict[str, Any]) -> ConfigDict:
    """Strict config; the examples show up in the OpenAPI schema."""
    return ConfigDict(extra="forbid", json_schema_extra={"examples": list(examples)})
