"""E2E test for `flint deploy` / `flint status` against a real (kind) cluster.

Gated on FLINT_E2E_KIND=1. Validates flint's orchestration -- render,
ensure-namespace, apply-in-order, and the label-based status reader -- by
asserting the Kubernetes objects are actually created in a live API server.

It does NOT run real vLLM inference (that needs a GPU). A stub image is used
and the rollout is not awaited, so pod scheduling/readiness is irrelevant;
the assertions are about resource creation, not model serving.

Requirements:
  - a reachable cluster (kind) via the current kubeconfig
  - kubectl on PATH
"""

from __future__ import annotations

import os
import signal
import subprocess
import time

import httpx
import pytest

_E2E_ENABLED = os.getenv("FLINT_E2E_KIND") == "1"
_NAMESPACE = "flint-e2e"
_MODEL = "demo"
_NAME = f"{_MODEL}-latest"  # deploy names resources {model}-{version}


def _run(*args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)


def _kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return _run("kubectl", *args)


@pytest.mark.skipif(not _E2E_ENABLED, reason="FLINT_E2E_KIND=1 not set")
def test_deploy_creates_objects_and_status_finds_them() -> None:
    try:
        deploy = _run(
            "flint",
            "deploy",
            _MODEL,
            "--image",
            "nginx:stable",
            "--gpu",
            "0",
            "--namespace",
            _NAMESPACE,
            "--no-wait",
        )
        assert deploy.returncode == 0, (
            f"deploy failed:\nSTDOUT:\n{deploy.stdout}\nSTDERR:\n{deploy.stderr}"
        )
        assert f"{_NAME}.{_NAMESPACE}.svc.cluster.local/v1" in deploy.stdout

        # Deployment, Service, and HPA must exist in the API server.
        assert _kubectl("get", "deploy", _NAME, "-n", _NAMESPACE).returncode == 0
        assert _kubectl("get", "svc", _NAME, "-n", _NAMESPACE).returncode == 0
        assert _kubectl("get", "hpa", _NAME, "-n", _NAMESPACE).returncode == 0

        # No HF-Hub weights were requested, so the weights PVC must NOT exist.
        assert (
            _kubectl("get", "pvc", f"{_MODEL}-weights", "-n", _NAMESPACE).returncode
            != 0
        )

        # `flint status` must find the deployment via its flint.dev/managed label.
        status = _run("flint", "status", _MODEL, "--namespace", _NAMESPACE)
        assert status.returncode == 0, status.stderr
        assert f"{_MODEL}:latest" in status.stdout

        # Idempotency: an identical re-deploy must not churn the Deployment.
        # Server-side apply with no field changes leaves the spec untouched, so
        # metadata.generation stays put (it only bumps on spec changes).
        gen1 = _kubectl(
            "get", "deploy", _NAME, "-n", _NAMESPACE,
            "-o", "jsonpath={.metadata.generation}",
        ).stdout
        redeploy = _run(
            "flint", "deploy", _MODEL, "--image", "nginx:stable",
            "--gpu", "0", "--namespace", _NAMESPACE, "--no-wait",
        )
        assert redeploy.returncode == 0, redeploy.stderr
        gen2 = _kubectl(
            "get", "deploy", _NAME, "-n", _NAMESPACE,
            "-o", "jsonpath={.metadata.generation}",
        ).stdout
        assert gen1 and gen1 == gen2, f"deploy not idempotent: gen {gen1!r} -> {gen2!r}"
    finally:
        _kubectl(
            "delete", "namespace", _NAMESPACE, "--ignore-not-found", "--wait=false"
        )


# -- Ollama real inference (CPU-capable, so this runs in CI) -------------------

_OLLAMA_NS = "flint-ollama-e2e"
_OLLAMA_MODEL = "tinyllama"
_OLLAMA_NAME = f"{_OLLAMA_MODEL}-latest"
_OLLAMA_PORT = 18434


@pytest.mark.skipif(not _E2E_ENABLED, reason="FLINT_E2E_KIND=1 not set")
def test_ollama_deploy_serves_real_inference() -> None:
    """Deploy a real model with the Ollama runtime and verify it serves.

    Ollama runs on CPU, so unlike vLLM this exercises real inference in CI:
    deploy tinyllama, wait for Ready, then hit /v1/chat/completions.
    """
    pf: subprocess.Popen[str] | None = None
    try:
        deploy = _run(
            "flint",
            "deploy",
            _OLLAMA_MODEL,
            "--runtime",
            "ollama",
            "--namespace",
            _OLLAMA_NS,
            "--wait",
            "--wait-timeout",
            "600",
            timeout=720,
        )
        assert deploy.returncode == 0, (
            f"deploy failed:\nSTDOUT:\n{deploy.stdout}\nSTDERR:\n{deploy.stderr}"
        )
        assert "rollout: ready" in deploy.stdout

        pf = subprocess.Popen(
            [
                "kubectl",
                "port-forward",
                f"svc/{_OLLAMA_NAME}",
                f"{_OLLAMA_PORT}:80",
                "-n",
                _OLLAMA_NS,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        base = f"http://localhost:{_OLLAMA_PORT}"
        deadline = time.monotonic() + 30
        reachable = False
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base}/api/tags", timeout=2.0).status_code == 200:
                    reachable = True
                    break
            except httpx.RequestError:
                pass
            time.sleep(1)
        assert reachable, "port-forward to the ollama service did not become reachable"

        resp = httpx.post(
            f"{base}/v1/chat/completions",
            json={
                "model": _OLLAMA_MODEL,
                "messages": [{"role": "user", "content": "Say hello in one word."}],
                "max_tokens": 16,
            },
            timeout=120.0,
        )
        assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
        content = resp.json()["choices"][0]["message"]["content"]
        assert content.strip(), "empty completion content"
    finally:
        if pf is not None and pf.poll() is None:
            pf.send_signal(signal.SIGTERM)
            pf.wait(timeout=10)
        _kubectl(
            "delete", "namespace", _OLLAMA_NS, "--ignore-not-found", "--wait=false"
        )
