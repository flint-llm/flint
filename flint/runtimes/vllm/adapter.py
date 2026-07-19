"""vLLM runtime adapter.

Owns everything vLLM-specific: the CUDA image, its templates, its OpenAI
server port, readiness probe, and default (GPU-oriented) resources. The
container args (``--model`` / ``--served-model-name``) live in the vLLM
deployment template under ``templates/runtimes/vllm/``.
"""

from __future__ import annotations

from flint.core.models import ReadinessProbe, ResourceSpec

# Pinned image tag for reproducible deploys. vLLM ships frequent releases;
# this is a recent stable tag verified present in the vllm/vllm-openai
# registry. Bump deliberately.
_IMAGE_TAG = "v0.25.1"


class VLLMAdapter:
    """RuntimeAdapter for vLLM (OpenAI-compatible, GPU)."""

    name = "vllm"
    template_subdir = "runtimes/vllm"

    def default_image(self) -> str:
        return f"vllm/vllm-openai:{_IMAGE_TAG}"

    def default_service_port(self) -> int:
        return 8080

    def default_resources(self) -> ResourceSpec:
        return ResourceSpec()

    def default_readiness_probe(self) -> ReadinessProbe:
        return ReadinessProbe(port=8080, path="/health")
