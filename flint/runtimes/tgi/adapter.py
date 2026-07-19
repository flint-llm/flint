"""TGI (Text Generation Inference) runtime adapter.

TGI serves an OpenAI-compatible Messages API on port 80. The model is given
via the ``MODEL_ID`` env var (an HF repo); TGI downloads it at startup into
``/data``. Like vLLM it is GPU-oriented (CUDA image), so real inference is
verified on a GPU cluster (gated), while CI runs an object-creation smoke test.
"""

from __future__ import annotations

from flint.core.models import ReadinessProbe, ResourceSpec

# Pinned image tag for reproducible deploys (latest stable at time of writing).
_IMAGE_TAG = "3.3.7"


class TGIAdapter:
    """RuntimeAdapter for TGI (OpenAI-compatible, GPU)."""

    name = "tgi"
    template_subdir = "runtimes/tgi"

    def default_image(self) -> str:
        return f"ghcr.io/huggingface/text-generation-inference:{_IMAGE_TAG}"

    def default_service_port(self) -> int:
        return 80

    def default_resources(self) -> ResourceSpec:
        return ResourceSpec()

    def default_readiness_probe(self) -> ReadinessProbe:
        return ReadinessProbe(port=80, path="/health")
