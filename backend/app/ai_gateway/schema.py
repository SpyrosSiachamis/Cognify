"""AI gateway shapes: a typed result for every call, and the config read from env.

No provider imports here.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.vocab import GatewayFailure

Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GatewayOk[T](StrictModel):
    """The model replied and the reply passed validation. Read by the calling service."""

    ok: Literal[True] = True
    value: T


class GatewayFallback[T](StrictModel):
    """The call failed; value is the safe fallback to use instead. Read by the calling service."""

    ok: Literal[False] = False
    value: T
    failure: GatewayFailure
    detail: str | None = None


type GatewayResult[T] = Annotated[GatewayOk[T] | GatewayFallback[T], Field(discriminator="ok")]


class GatewayConfig(StrictModel):
    """Read from env at startup. model_id_variable is the NAME of the env variable holding the model ID."""

    region: Text  # from AWS_REGION
    model_id_variable: Text
