"""Gated real-inference E2E for `flint deploy` on a GPU cluster.

Gated on FLINT_E2E_GPU=1. Unlike the kind smoke test (which only asserts the
Kubernetes objects are created), this deploys a real small model with vLLM,
waits for the pod to become Ready, and verifies `/v1/chat/completions` returns
a valid response.

Why this is separate from CI: vLLM publishes no CPU image (`vllm/vllm-openai`
is CUDA-only), and building one from source is impractical per-PR. So real
inference is verified manually on a GPU-capable cluster, satisfying the build
plan's S3 exit criteria 1/2/5, while CI keeps the object-creation smoke test.

Requirements:
  - a GPU-capable cluster reachable via the current kubeconfig
  - kubectl on PATH
  - cluster network egress for HuggingFace weight prefetch (facebook/opt-125m)

Run:
    FLINT_E2E_GPU=1 pytest tests/integration/test_deploy_gpu.py -v
"""

from __future__ import annotations

import os
import signal
import subprocess
import time

import httpx
import pytest

_E2E_ENABLED = os.getenv("FLINT_E2E_GPU") == "1"
_NAMESPACE = "flint-gpu-e2e"
_MODEL = "opt-125m"
_HF_REPO = "facebook/opt-125m"
_NAME = f"{_MODEL}-latest"
_LOCAL_PORT = 18080
_BASE = f"http://localhost:{_LOCAL_PORT}"
_DEPLOY_TIMEOUT = 900  # weight download + model load can take a while


def _run(*args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)


def _kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return _run("kubectl", *args)


@pytest.mark.skipif(not _E2E_ENABLED, reason="FLINT_E2E_GPU=1 not set")
def test_deploy_serves_real_inference() -> None:
    pf: subprocess.Popen[str] | None = None
    try:
        deploy = _run(
            "flint",
            "deploy",
            _MODEL,
            "--hf-repo",
            _HF_REPO,
            "--gpu",
            "1",
            "--namespace",
            _NAMESPACE,
            "--wait",
            "--wait-timeout",
            str(_DEPLOY_TIMEOUT),
            timeout=_DEPLOY_TIMEOUT + 120,
        )
        assert deploy.returncode == 0, (
            f"deploy failed:\nSTDOUT:\n{deploy.stdout}\nSTDERR:\n{deploy.stderr}"
        )
        assert "rollout: ready" in deploy.stdout

        # The Service is ClusterIP; port-forward it to reach it from the test.
        pf = subprocess.Popen(
            [
                "kubectl",
                "port-forward",
                f"svc/{_NAME}",
                f"{_LOCAL_PORT}:80",
                "-n",
                _NAMESPACE,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 30
        reachable = False
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{_BASE}/health", timeout=2.0).status_code < 500:
                    reachable = True
                    break
            except httpx.RequestError:
                pass
            time.sleep(1)
        assert reachable, "port-forward to the service did not become reachable"

        resp = httpx.post(
            f"{_BASE}/v1/chat/completions",
            json={
                "model": _MODEL,  # --served-model-name is the model name
                "messages": [{"role": "user", "content": "Say hello in one word."}],
                "max_tokens": 16,
            },
            timeout=60.0,
        )
        assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
        content = resp.json()["choices"][0]["message"]["content"]
        assert content.strip(), "empty completion content"
    finally:
        if pf is not None and pf.poll() is None:
            pf.send_signal(signal.SIGTERM)
            pf.wait(timeout=10)
        _kubectl(
            "delete", "namespace", _NAMESPACE, "--ignore-not-found", "--wait=false"
        )


_TGI_NAMESPACE = "flint-tgi-gpu-e2e"
_TGI_MODEL = "opt-125m"
_TGI_HF_REPO = "facebook/opt-125m"
_TGI_NAME = f"{_TGI_MODEL}-latest"
_TGI_LOCAL_PORT = 18081
_TGI_BASE = f"http://localhost:{_TGI_LOCAL_PORT}"


@pytest.mark.skipif(not _E2E_ENABLED, reason="FLINT_E2E_GPU=1 not set")
def test_tgi_deploy_serves_real_inference() -> None:
    """Deploy a real model with the TGI runtime on a GPU cluster and verify it."""
    pf: subprocess.Popen[str] | None = None
    try:
        deploy = _run(
            "flint", "deploy", _TGI_MODEL,
            "--runtime", "tgi",
            "--hf-repo", _TGI_HF_REPO,
            "--gpu", "1",
            "--namespace", _TGI_NAMESPACE,
            "--wait", "--wait-timeout", str(_DEPLOY_TIMEOUT),
            timeout=_DEPLOY_TIMEOUT + 120,
        )
        assert deploy.returncode == 0, (
            f"deploy failed:\nSTDOUT:\n{deploy.stdout}\nSTDERR:\n{deploy.stderr}"
        )
        assert "rollout: ready" in deploy.stdout

        pf = subprocess.Popen(
            ["kubectl", "port-forward", f"svc/{_TGI_NAME}",
             f"{_TGI_LOCAL_PORT}:80", "-n", _TGI_NAMESPACE],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + 30
        reachable = False
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{_TGI_BASE}/health", timeout=2.0).status_code < 500:
                    reachable = True
                    break
            except httpx.RequestError:
                pass
            time.sleep(1)
        assert reachable, "port-forward to the TGI service did not become reachable"

        resp = httpx.post(
            f"{_TGI_BASE}/v1/chat/completions",
            json={
                "model": _TGI_MODEL,  # TGI serves the loaded MODEL_ID
                "messages": [{"role": "user", "content": "Say hello in one word."}],
                "max_tokens": 16,
            },
            timeout=60.0,
        )
        assert resp.status_code == 200, f"{resp.status_code}: {resp.text}"
        content = resp.json()["choices"][0]["message"]["content"]
        assert content.strip(), "empty completion content"
    finally:
        if pf is not None and pf.poll() is None:
            pf.send_signal(signal.SIGTERM)
            pf.wait(timeout=10)
        _kubectl("delete", "namespace", _TGI_NAMESPACE, "--ignore-not-found", "--wait=false")
