import pytest
from pydantic import TypeAdapter, ValidationError

from app.services.ai_gateway.schema import GatewayConfig, GatewayFallback, GatewayOk, GatewayResult


def test_ok_and_fallback_results():
    adapter = TypeAdapter(GatewayResult[int])
    assert isinstance(adapter.validate_python({"ok": True, "value": 1}), GatewayOk)
    fallback = adapter.validate_python({"ok": False, "value": 0, "failure": "timeout"})
    assert isinstance(fallback, GatewayFallback) and fallback.failure == "timeout"


def test_fallback_needs_a_known_failure_reason():
    with pytest.raises(ValidationError):
        TypeAdapter(GatewayResult[int]).validate_python({"ok": False, "value": 0, "failure": "bad vibes"})
    with pytest.raises(ValidationError):
        TypeAdapter(GatewayResult[int]).validate_python({"ok": False, "value": 0})


def test_value_is_typed():
    with pytest.raises(ValidationError):
        TypeAdapter(GatewayResult[int]).validate_python({"ok": True, "value": "not a number"})


def test_config():
    config = GatewayConfig(region="eu-central-1", model_id_variable="BEDROCK_MODEL_ID")
    assert config.region == "eu-central-1"
    with pytest.raises(ValidationError):
        GatewayConfig(region="", model_id_variable="X")
    with pytest.raises(ValidationError):
        GatewayConfig(region="eu-central-1", model_id_variable="X", api_key="secret")
