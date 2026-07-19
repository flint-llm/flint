"""Tests for the runtime adapter protocol and registry."""

from __future__ import annotations

import pytest

from flint.core.errors import UnsupportedRuntimeError
from flint.core.models import ReadinessProbe, ResourceSpec
from flint.runtimes import RuntimeAdapter, get_adapter, supported_runtimes
from flint.runtimes.ollama import OllamaAdapter
from flint.runtimes.tgi import TGIAdapter
from flint.runtimes.vllm import VLLMAdapter

# -- registry -----------------------------------------------------------------


def test_get_adapter_vllm() -> None:
    adapter = get_adapter("vllm")
    assert adapter.name == "vllm"


def test_get_adapter_unknown_raises() -> None:
    with pytest.raises(UnsupportedRuntimeError, match="Unsupported runtime"):
        get_adapter("nonexistent")


def test_supported_runtimes_includes_all_three() -> None:
    assert set(supported_runtimes()) >= {"vllm", "ollama", "tgi"}


def test_adapters_satisfy_protocol() -> None:
    assert isinstance(VLLMAdapter(), RuntimeAdapter)
    assert isinstance(OllamaAdapter(), RuntimeAdapter)
    assert isinstance(TGIAdapter(), RuntimeAdapter)


def test_get_adapter_ollama_and_tgi() -> None:
    assert get_adapter("ollama").name == "ollama"
    assert get_adapter("tgi").name == "tgi"


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


# -- Ollama adapter -----------------------------------------------------------


def test_ollama_defaults() -> None:
    adapter = OllamaAdapter()
    assert adapter.template_subdir == "runtimes/ollama"
    assert adapter.default_service_port() == 11434
    assert adapter.default_resources().gpu_count == 0  # CPU by default
    probe = adapter.default_readiness_probe()
    assert probe.port == 11434
    assert probe.path == "/api/tags"


def test_ollama_image_pinned_not_latest() -> None:
    img = OllamaAdapter().default_image()
    assert "ollama/ollama" in img
    assert img.rsplit(":", 1)[-1] != "latest"


# -- TGI adapter --------------------------------------------------------------


def test_tgi_defaults() -> None:
    adapter = TGIAdapter()
    assert adapter.template_subdir == "runtimes/tgi"
    assert adapter.default_service_port() == 80
    probe = adapter.default_readiness_probe()
    assert probe.port == 80
    assert probe.path == "/health"


def test_tgi_image_pinned_not_latest() -> None:
    img = TGIAdapter().default_image()
    assert "text-generation-inference" in img
    assert img.rsplit(":", 1)[-1] != "latest"
