"""The one door to the model (rule 4): build the configured model, and run every agent call
with a timeout, so a failure comes back as a typed fallback instead of an exception.

This is the only module that imports the provider.
"""

import asyncio
import os
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models import Model

from .schema import GatewayConfig, GatewayFallback, GatewayOk

DEFAULT_TIMEOUT_SECONDS = 45.0


def config(model_id_variable: str = "TUTOR_MODEL_ID") -> GatewayConfig:
    return GatewayConfig(region=os.environ["AWS_REGION"], model_id_variable=model_id_variable)


@lru_cache
def model_for(model_id_variable: str = "TUTOR_MODEL_ID") -> Model:
    """The Bedrock model named by the env variable. Swapping the model is an env change."""
    from pydantic_ai.models.bedrock import BedrockConverseModel
    from pydantic_ai.providers.bedrock import BedrockProvider

    cfg = config(model_id_variable)
    model_id = os.environ.get(cfg.model_id_variable)
    if not model_id:
        raise RuntimeError(f"{cfg.model_id_variable} is not set")
    # boto3 ignores AWS_REGION, so the region is passed explicitly.
    return BedrockConverseModel(model_id, provider=BedrockProvider(region_name=cfg.region))


async def call[T](
    agent: Agent[Any, T],
    prompt: str,
    *,
    model: Model,
    fallback: T,
    deps: Any = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> GatewayOk[T] | GatewayFallback[T]:
    """Run one agent call. Validation retries happen inside the agent (its retries setting)."""
    try:
        result = await asyncio.wait_for(agent.run(prompt, model=model, deps=deps), timeout)
    except TimeoutError:
        return GatewayFallback(value=fallback, failure="timeout", detail=f"no reply within {timeout}s")
    except UnexpectedModelBehavior as exc:
        return GatewayFallback(value=fallback, failure="invalid_output", detail=str(exc))
    except ModelAPIError as exc:
        return GatewayFallback(value=fallback, failure="provider_error", detail=str(exc))
    return GatewayOk(value=result.output)
