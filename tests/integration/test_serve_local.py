"""E2E test for `flint serve` with a real Ollama installation.

Gated on the FLINT_E2E_OLLAMA=1 environment variable. The unit test suite
runs without Ollama installed; this test requires it.

To run locally:
    FLINT_E2E_OLLAMA=1 pytest tests/integration/test_serve_local.py -v

Requirements:
  - ollama installed and on PATH
  - tinyllama model pre-pulled: ollama pull tinyllama
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time

import httpx
import pytest

_E2E_ENABLED = os.getenv("FLINT_E2E_OLLAMA") == "1"
_MODEL = "tinyllama"
_PORT = 11435  # use a non-default port to avoid conflicts
_BASE_URL = f"http://localhost:{_PORT}"
_HEALTH_URL = f"{_BASE_URL}/api/tags"
_CHAT_URL = f"{_BASE_URL}/v1/chat/completions"
_STARTUP_TIMEOUT = 120  # seconds — model load can take a while
_SHUTDOWN_TIMEOUT = 10  # seconds


def _wait_for_url(url: str, timeout: float) -> bool:
    """Poll *url* until it returns 200 or *timeout* seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(1)
    return False


@pytest.mark.skipif(not _E2E_ENABLED, reason="FLINT_E2E_OLLAMA=1 not set")
def test_serve_tinyllama_happy_path() -> None:
    """Start flint serve, hit the endpoint, verify streaming, shutdown cleanly."""
    proc = subprocess.Popen(
        ["flint", "serve", _MODEL, "--port", str(_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for the server to be healthy
        healthy = _wait_for_url(_HEALTH_URL, _STARTUP_TIMEOUT)
        assert healthy, (
            f"Ollama server did not become healthy within {_STARTUP_TIMEOUT}s. "
            f"Check that tinyllama is pulled: ollama pull {_MODEL}"
        )

        # Send a streaming chat request
        payload = {
            "model": _MODEL,
            "stream": True,
            "messages": [{"role": "user", "content": "Say 'hello' in one word."}],
        }
        chunks_received = 0
        with httpx.stream(
            "POST",
            _CHAT_URL,
            json=payload,
            timeout=60.0,
            headers={"Content-Type": "application/json"},
        ) as resp:
            assert resp.status_code == 200, (
                f"Expected 200 from /v1/chat/completions, got {resp.status_code}"
            )
            for raw_line in resp.iter_lines():
                line = raw_line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("choices"):
                        chunks_received += 1

        assert chunks_received > 0, "Expected at least one SSE chunk from streaming response"

    finally:
        # Send SIGTERM and verify clean exit
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=_SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                pytest.fail(f"flint serve did not exit within {_SHUTDOWN_TIMEOUT}s after SIGTERM")

    # Verify no zombie ollama processes
    check = subprocess.run(
        ["pgrep", "-x", "ollama"],
        capture_output=True,
        text=True,
    )
    zombie_pids = check.stdout.strip()
    assert not zombie_pids, (
        f"Found lingering ollama process(es) after shutdown: {zombie_pids}"
    )


@pytest.mark.skipif(not _E2E_ENABLED, reason="FLINT_E2E_OLLAMA=1 not set")
def test_serve_sigterm_exits_cleanly() -> None:
    """SIGTERM causes flint serve to exit 0 within the timeout."""
    proc = subprocess.Popen(
        ["flint", "serve", _MODEL, "--port", str(_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        healthy = _wait_for_url(_HEALTH_URL, _STARTUP_TIMEOUT)
        assert healthy, "Server did not start"
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            ret = proc.wait(timeout=_SHUTDOWN_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("SIGTERM did not result in clean exit")

    assert ret == 0, f"Expected exit code 0, got {ret}"
