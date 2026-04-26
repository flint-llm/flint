"""Local Ollama subprocess wrapper for `flint serve`.

Exposes a small procedural API:
  - is_available()       -- check ollama is on PATH
  - list_local_models()  -- models already pulled
  - pull()               -- stream pull progress
  - serve()              -- start the Ollama server subprocess
  - wait_healthy()       -- block until the server is accepting requests

All functions that spawn subprocesses or make network calls follow
CONVENTIONS.md: no print(), typed exceptions from flint.core.errors,
warnings.catch_warnings around any k8s calls (none here, but pattern noted).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from collections.abc import Iterator

import httpx

from flint.core.errors import OllamaError, OllamaNotFoundError, OllamaUnhealthyError

logger = logging.getLogger(__name__)

DEFAULT_PORT: int = 11434
_HEALTH_PATH: str = "/api/tags"


# -- Public API ---------------------------------------------------------------


def is_available() -> bool:
    """Return True if the ollama binary is on PATH."""
    return shutil.which("ollama") is not None


def list_local_models() -> list[str]:
    """Return locally available model names (without tags for matching).

    Runs `ollama list` and parses the output. Returns an empty list if the
    command fails (e.g. no running server) rather than raising.

    Output format:
        NAME               ID              SIZE      MODIFIED
        tinyllama:latest   2644915ede35    637 MB    2 weeks ago
    """
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        logger.debug(
            "ollama list failed (exit %d): %s", result.returncode, result.stderr.strip()
        )
        return []

    models: list[str] = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.split()
        if parts:
            models.append(parts[0])  # full name including tag
    return models


def is_model_local(model: str) -> bool:
    """Return True if *model* is in the local model library.

    Normalises the model name to include a tag (defaults to :latest) before
    comparing against the output of list_local_models().
    """
    normalised = _normalise_model(model)
    local = list_local_models()
    return normalised in local or model in local


def pull(model: str) -> Iterator[str]:
    """Pull *model* from the Ollama registry and yield progress lines.

    Requires `ollama serve` to be running (Ollama CLI communicates with its
    daemon for pull operations). The caller iterates the returned generator
    to stream progress output.

    Raises OllamaError after iteration is exhausted if the pull failed.
    """
    logger.debug("Pulling model: %s", model)
    proc = subprocess.Popen(
        ["ollama", "pull", model],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            yield line.rstrip()
    finally:
        proc.wait()

    if proc.returncode != 0:
        raise OllamaError(
            f"Failed to pull model {model!r} (ollama pull exited {proc.returncode}). "
            "Is 'ollama serve' running?"
        )


def serve(model: str, port: int = DEFAULT_PORT) -> subprocess.Popen[str]:
    """Start `ollama serve` and return the Popen handle.

    The caller is responsible for managing the process lifecycle (waiting for
    health, streaming output, and shutting down). The model name is provided
    here for logging only — Ollama serves all local models from one daemon.

    Sets OLLAMA_HOST to bind on the given port.
    """
    if not is_available():
        raise OllamaNotFoundError(
            "ollama is not installed or not on PATH. "
            "Install: brew install ollama (macOS) "
            "or curl -fsSL https://ollama.com/install.sh | sh (Linux)"
        )

    env = {**os.environ, "OLLAMA_HOST": f"0.0.0.0:{port}"}
    logger.debug("Starting ollama serve on port %d for model %s", port, model)
    proc: subprocess.Popen[str] = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    return proc


def wait_healthy(port: int = DEFAULT_PORT, timeout_s: int = 30) -> None:
    """Poll the Ollama health endpoint until it responds 200 or times out.

    Raises OllamaUnhealthyError if the server doesn't respond within
    *timeout_s* seconds.
    """
    url = f"http://localhost:{port}{_HEALTH_PATH}"
    deadline = time.monotonic() + timeout_s
    logger.debug("Waiting for Ollama to be healthy at %s (timeout %ds)", url, timeout_s)
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                logger.debug("Ollama is healthy")
                return
        except httpx.RequestError:
            pass
        time.sleep(0.5)

    raise OllamaUnhealthyError(
        f"Ollama server did not become healthy within {timeout_s}s "
        f"(port {port}). Check 'ollama serve' logs for errors."
    )


# -- Private helpers ----------------------------------------------------------


def _normalise_model(model: str) -> str:
    """Ensure a model name has an explicit tag (default: latest)."""
    if ":" not in model:
        return f"{model}:latest"
    return model
