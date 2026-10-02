"""The one door to the model (rule 4): build the configured model, and run every agent call
with a timeout, so a failure comes back as a typed fallback instead of an exception.

This is the only module that imports the provider.
"""

import asyncio
import logging
import os
import time
from functools import lru_cache
from typing import Any

from botocore.exceptions import BotoCoreError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models import Model

from app.common import trace

from .schema import GatewayConfig, GatewayFallback, GatewayOk

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 45.0


def config_problems(model_id_variable: str = "TUTOR_MODEL_ID") -> list[str]:
    """What is missing for the real model to work. Checked at startup; makes no network call."""
    import boto3

    problems = []
    if not os.environ.get(model_id_variable):
        problems.append(f"{model_id_variable} is not set")
    region = os.environ.get("AWS_REGION")
    if not region:
        problems.append("AWS_REGION is not set")
    if boto3.Session(region_name=region).get_credentials() is None:
        problems.append("no AWS credentials found (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)")
    return problems


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
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(agent.run(prompt, model=model, deps=deps), timeout)
    except asyncio.CancelledError:
        # Not a model failure: a caller's time limit stopped the call. Recorded, then passed on unchanged.
        _trace_call(agent, model, started, "cancelled")
        raise
    except TimeoutError:
        _trace_call(agent, model, started, "timeout", timeout_seconds=timeout)
        return GatewayFallback(value=fallback, failure="timeout", detail=f"no reply within {timeout}s")
    except UnexpectedModelBehavior as exc:
        _trace_call(agent, model, started, "invalid_output", detail=str(exc))
        return GatewayFallback(value=fallback, failure="invalid_output", detail=str(exc))
    except (ModelAPIError, BotoCoreError) as exc:
        # BotoCoreError: failures before or around the HTTP call that the model library does not wrap
        # (missing credentials, connection and read timeouts, endpoint errors).
        _trace_call(agent, model, started, "provider_error", error=exc)
        return GatewayFallback(value=fallback, failure="provider_error", detail=f"{type(exc).__name__}: {exc}")
    _trace_call(agent, model, started, "ok", result=result)
    return GatewayOk(value=result.output)


def _provider_error(exc: Exception) -> tuple[str, dict[str, Any]]:
    """What the provider said, for the trace: the HTTP status, its error code and request id (never headers)."""
    if not isinstance(exc, ModelHTTPError):
        return "provider_connection_error", {"detail": f"{type(exc).__name__}: {exc}"}
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("Error") if isinstance(body.get("Error"), dict) else {}
    meta = body.get("ResponseMetadata") if isinstance(body.get("ResponseMetadata"), dict) else {}
    return "provider_http_error", {
        "http_status": exc.status_code,
        "provider_error_code": error.get("Code"),
        "provider_error_message": error.get("Message"),
        "request_id": meta.get("RequestId"),
        "sdk_retry_attempts": meta.get("RetryAttempts"),
        "transient": exc.status_code == 429 or exc.status_code >= 500,
    }


def _trace_call(
    agent: Agent[Any, Any], model: Model, started: float, outcome: str, result: Any = None,
    error: Exception | None = None, **fields: Any,
) -> None:
    """One MODEL_CALL event. Tracing never changes the call: anything that goes wrong here is only logged."""
    if not trace.active():
        return
    try:
        if error is not None:
            outcome, provider_fields = _provider_error(error)
            fields |= provider_fields
        if result is not None:
            usage = result.usage
            fields |= {"requests": usage.requests, "input_tokens": usage.input_tokens,
                       "output_tokens": usage.output_tokens}
        trace.record(
            trace.ModelCall, operation=agent.name, provider=model.system, model=model.model_name, outcome=outcome,
            latency_ms=round((time.monotonic() - started) * 1000), **fields,
        )
    except Exception:
        log.error("trace: could not record a model call", exc_info=True)
