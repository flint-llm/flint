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
import subprocess

import pytest

_E2E_ENABLED = os.getenv("FLINT_E2E_KIND") == "1"
_NAMESPACE = "flint-e2e"
_MODEL = "demo"
_NAME = f"{_MODEL}-latest"  # deploy names resources {model}-{version}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), capture_output=True, text=True)


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
