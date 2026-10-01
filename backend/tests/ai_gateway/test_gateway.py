"""The gateway turns every provider failure into a typed fallback (no exception escapes)."""

import asyncio

import pytest
from botocore.exceptions import EndpointConnectionError, NoCredentialsError, ReadTimeoutError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.function import FunctionModel

from app.ai_gateway import gateway


def failing(exc: Exception) -> FunctionModel:
    def respond(messages, info):
        raise exc

    return FunctionModel(respond)


@pytest.mark.parametrize(
    ("exc", "failure"),
    [
        (NoCredentialsError(), "provider_error"),
        (EndpointConnectionError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"), "provider_error"),
        (ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"), "provider_error"),
        (ModelHTTPError(status_code=403, model_name="m", body="AccessDenied"), "provider_error"),
    ],
    ids=["no-credentials", "no-connection", "read-timeout", "access-denied"],
)
def test_provider_failures_become_fallbacks(exc, failure):
    result = asyncio.run(gateway.call(Agent(output_type=str), "hi", model=failing(exc), fallback="safe"))
    assert (result.ok, result.failure, result.value) == (False, failure, "safe")


def test_invalid_output_becomes_a_fallback():
    def nonsense(messages, info):
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"wrong": 1})])

    agent = Agent(output_type=int, retries=1)
    result = asyncio.run(gateway.call(agent, "hi", model=FunctionModel(nonsense), fallback=0))
    assert (result.ok, result.failure) == (False, "invalid_output")


def test_timeout_becomes_a_fallback():
    async def slow(messages, info):
        await asyncio.sleep(1)

    result = asyncio.run(gateway.call(Agent(output_type=str), "hi", model=FunctionModel(slow), fallback="safe",
                                      timeout=0.05))
    assert (result.ok, result.failure) == (False, "timeout")


def test_config_problems_name_what_is_missing(monkeypatch):
    monkeypatch.delenv("TUTOR_MODEL_ID", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/nonexistent")
    monkeypatch.setenv("AWS_CONFIG_FILE", "/nonexistent")
    problems = " | ".join(gateway.config_problems())
    assert "TUTOR_MODEL_ID" in problems and "AWS_REGION" in problems and "credentials" in problems


def test_startup_refuses_a_real_tutor_that_cannot_work(monkeypatch):
    from app.main import check_tutor_config

    monkeypatch.setenv("TUTOR_MODEL_ID", "some.model")
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(RuntimeError, match="AWS_REGION is not set"):
        check_tutor_config()


def test_startup_without_a_model_is_the_offline_stub(monkeypatch):
    from app.main import check_tutor_config

    monkeypatch.delenv("TUTOR_MODEL_ID", raising=False)
    assert check_tutor_config() == "stub"
