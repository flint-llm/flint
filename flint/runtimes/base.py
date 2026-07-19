"""RuntimeAdapter protocol — the abstraction each deployable runtime implements.

A ``RuntimeAdapter`` tells the deploy flow everything runtime-specific:
which image and manifest templates to use, which port and readiness probe the
server exposes, and sensible default resources. Runtime-specific *container*
wiring (args, env, weight handling) lives in that runtime's templates under
``templates/runtimes/<name>/`` — the adapter selects the template directory and
supplies the defaults those templates render against.

To add a runtime: implement this protocol and register the adapter in
``flint/runtimes/registry.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flint.core.models import ReadinessProbe, ResourceSpec


@runtime_checkable
class RuntimeAdapter(Protocol):
    """What the deploy flow needs to know to deploy a model on a runtime."""

    #: Runtime identifier, e.g. ``"vllm"`` (matches ``--runtime``).
    name: str
    #: Template directory relative to the templates root, e.g. ``"runtimes/vllm"``.
    template_subdir: str

    def default_image(self) -> str:
        """The container image used when ``--image`` is not given."""
        ...

    def default_service_port(self) -> int:
        """The port the runtime's HTTP server listens on inside the pod."""
        ...

    def default_resources(self) -> ResourceSpec:
        """Sensible default CPU/memory/GPU requests for this runtime."""
        ...

    def default_readiness_probe(self) -> ReadinessProbe:
        """The readiness probe (path + port) for this runtime's server."""
        ...
