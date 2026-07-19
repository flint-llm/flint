"""Runtime adapter registry — resolve a runtime name to its adapter."""

from __future__ import annotations

from flint.core.errors import UnsupportedRuntimeError
from flint.runtimes.base import RuntimeAdapter
from flint.runtimes.vllm import VLLMAdapter

_ADAPTERS: dict[str, RuntimeAdapter] = {
    VLLMAdapter.name: VLLMAdapter(),
}


def get_adapter(runtime: str) -> RuntimeAdapter:
    """Return the adapter for *runtime*, or raise UnsupportedRuntimeError."""
    adapter = _ADAPTERS.get(runtime)
    if adapter is None:
        raise UnsupportedRuntimeError(
            f"Unsupported runtime {runtime!r}. "
            f"Supported: {', '.join(supported_runtimes())}."
        )
    return adapter


def supported_runtimes() -> list[str]:
    """Return the sorted list of registered runtime names."""
    return sorted(_ADAPTERS)
