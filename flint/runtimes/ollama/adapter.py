"""Ollama runtime adapter.

Ollama runs on CPU (no GPU required), exposes an OpenAI-compatible API on
port 11434, and pulls models from the Ollama registry by tag (the model name).
Its deployment template pulls the model in an init container into an emptyDir,
then serves it — so no HuggingFace repo or weights PVC is involved.
"""

from __future__ import annotations

from flint.core.models import ReadinessProbe, ResourceSpec

# Pinned image tag for reproducible deploys (latest stable at time of writing).
_IMAGE_TAG = "0.32.1"


class OllamaAdapter:
    """RuntimeAdapter for Ollama (OpenAI-compatible, CPU-capable)."""

    name = "ollama"
    template_subdir = "runtimes/ollama"

    def default_image(self) -> str:
        return f"ollama/ollama:{_IMAGE_TAG}"

    def default_service_port(self) -> int:
        return 11434

    def default_resources(self) -> ResourceSpec:
        # Ollama serves on CPU by default (no GPU requested).
        return ResourceSpec()

    def default_readiness_probe(self) -> ReadinessProbe:
        # /api/tags returns 200 once the daemon is up; the model is already
        # present (pulled by the init container before the main container).
        return ReadinessProbe(port=11434, path="/api/tags")
