"""Tests for flint.core.models."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from flint.core.errors import WeightsValidationError
from flint.core.models import (
    SCHEMA_VERSION,
    ModelRef,
    ReadinessProbe,
    RenderContext,
    ResourceSpec,
    TrafficSplit,
    TrafficWeight,
    WeightsStrategy,
    decode_base64,
    is_base64_encoded,
    normalize_model_name,
    validate_traffic_weights,
)

# -- normalize_model_name -----------------------------------------------------


def test_normalize_lower() -> None:
    assert normalize_model_name("Llama-3") == "llama-3"


def test_normalize_already_lower() -> None:
    assert normalize_model_name("mistral") == "mistral"


def test_normalize_converts_to_str() -> None:
    assert normalize_model_name("1") == "1"


# -- validate_traffic_weights -------------------------------------------------


def test_weights_valid() -> None:
    validate_traffic_weights({"a": 90, "b": 10})


def test_weights_single_100() -> None:
    validate_traffic_weights({"v1": 100})


def test_weights_empty_sum_zero() -> None:
    with pytest.raises(WeightsValidationError, match="sum to 0"):
        validate_traffic_weights({})


def test_weights_not_100() -> None:
    with pytest.raises(WeightsValidationError, match="sum to 50"):
        validate_traffic_weights({"a": 50})


def test_weights_over_100() -> None:
    with pytest.raises(WeightsValidationError, match="sum to 110"):
        validate_traffic_weights({"a": 60, "b": 50})


# -- is_base64_encoded / decode_base64 ----------------------------------------


def test_is_base64_str_true() -> None:
    encoded = base64.b64encode(b"hello world").decode()
    assert is_base64_encoded(encoded) is True


def test_is_base64_bytes_true() -> None:
    encoded = base64.b64encode(b"hello world")
    assert is_base64_encoded(encoded) is True


def test_is_base64_plain_text_false() -> None:
    assert is_base64_encoded("this is not base64!!!!") is False


def test_decode_base64_str() -> None:
    encoded = base64.b64encode(b"hello").decode()
    assert decode_base64(encoded) == "hello"


def test_decode_base64_bytes() -> None:
    encoded = base64.b64encode(b"flint")
    assert decode_base64(encoded) == "flint"


# -- ModelRef -----------------------------------------------------------------


def test_model_ref_normalises_name() -> None:
    ref = ModelRef(name="Llama-3.2", version="V1")
    assert ref.name == "llama-3.2"
    assert ref.version == "v1"


def test_model_ref_defaults() -> None:
    ref = ModelRef(name="mistral")
    assert ref.version == "latest"
    assert ref.image is None
    assert ref.weights_strategy == WeightsStrategy.HF_HUB


def test_model_ref_with_image() -> None:
    ref = ModelRef(name="mistral", image="vllm/vllm-openai:latest")
    assert ref.image == "vllm/vllm-openai:latest"


# -- ResourceSpec -------------------------------------------------------------


def test_resource_spec_defaults() -> None:
    spec = ResourceSpec()
    assert spec.gpu_count == 0
    assert spec.gpu_type == "nvidia.com/gpu"


def test_resource_spec_gpu() -> None:
    spec = ResourceSpec(gpu_count=2, gpu_type="amd.com/gpu")
    assert spec.gpu_count == 2


def test_resource_spec_invalid_gpu_count() -> None:
    with pytest.raises(ValidationError):
        ResourceSpec(gpu_count=-1)


# -- ReadinessProbe -----------------------------------------------------------


def test_readiness_probe_defaults() -> None:
    probe = ReadinessProbe()
    assert probe.port == 8080
    assert probe.path == "/health"
    assert probe.initial_delay_seconds == 30


def test_readiness_probe_invalid_port_zero() -> None:
    with pytest.raises(ValidationError):
        ReadinessProbe(port=0)


def test_readiness_probe_invalid_port_high() -> None:
    with pytest.raises(ValidationError):
        ReadinessProbe(port=65536)


# -- RenderContext ------------------------------------------------------------


def test_render_context_minimal() -> None:
    ctx = RenderContext(
        model_name="mistral",
        model_version="v1",
        runtime="vllm",
        image="vllm/vllm-openai:latest",
    )
    assert ctx.namespace == "flint"
    assert ctx.replicas == 1


def test_render_context_schema_version() -> None:
    ctx = RenderContext(
        model_name="m", model_version="v1", runtime="vllm", image="img"
    )
    assert ctx.schema_version == SCHEMA_VERSION


def test_render_context_custom_resources() -> None:
    ctx = RenderContext(
        model_name="m",
        model_version="v1",
        runtime="vllm",
        image="img",
        resources=ResourceSpec(gpu_count=1),
    )
    assert ctx.resources.gpu_count == 1


# -- TrafficSplit -------------------------------------------------------------


def test_traffic_split_valid() -> None:
    split = TrafficSplit(
        model_name="llama",
        weights=[
            TrafficWeight(version="v1", weight=70),
            TrafficWeight(version="v2", weight=30),
        ],
    )
    assert split.model_name == "llama"


def test_traffic_split_invalid_sum() -> None:
    with pytest.raises(ValidationError, match="sum to 50"):
        TrafficSplit(
            model_name="llama",
            weights=[TrafficWeight(version="v1", weight=50)],
        )


def test_traffic_weight_over_100() -> None:
    with pytest.raises(ValidationError):
        TrafficWeight(version="v1", weight=101)


def test_traffic_weight_negative() -> None:
    with pytest.raises(ValidationError):
        TrafficWeight(version="v1", weight=-1)
