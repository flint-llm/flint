"""Tests for the runtime adapter protocol and registry."""

from __future__ import annotations

import pytest

from flint.core.errors import UnsupportedRuntimeError
from flint.core.models import ReadinessProbe, ResourceSpec
from flint.runtimes import RuntimeAdapter, get_adapter, supported_runtimes
from flint.runtimes.vllm import VLLMAdapter

# -- registry -----------------------------------------------------------------


def test_get_adapter_vllm() -> None:
    adapter = get_adapter("vllm")
    assert adapter.name == "vllm"


def test_get_adapter_unknown_raises() -> None:
    with pytest.raises(UnsupportedRuntimeError, match="Unsupported runtime"):
        get_adapter("nonexistent")


def test_supported_runtimes_includes_vllm() -> None:
    assert "vllm" in supported_runtimes()


def test_vllm_satisfies_protocol() -> None:
    assert isinstance(VLLMAdapter(), RuntimeAdapter)


# -- vLLM adapter -------------------------------------------------------------


def test_vllm_image_pinned_not_latest() -> None:
    # Reproducible deploys: the vLLM image must carry a concrete version tag.
    img = VLLMAdapter().default_image()
    assert "vllm/vllm-openai" in img
    tag = img.rsplit(":", 1)[-1]
    assert tag != "latest"
    assert tag.startswith("v")


def test_vllm_defaults() -> None:
    adapter = VLLMAdapter()
    assert adapter.template_subdir == "runtimes/vllm"
    assert adapter.default_service_port() == 8080
    assert isinstance(adapter.default_resources(), ResourceSpec)
    probe = adapter.default_readiness_probe()
    assert isinstance(probe, ReadinessProbe)
    assert probe.path == "/health"
    assert probe.port == 8080
