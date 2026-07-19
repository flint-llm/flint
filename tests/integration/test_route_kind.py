"""E2E test for `flint route` against kind + Envoy Gateway.

Gated on FLINT_E2E_ROUTE=1. Exercises the whole traffic-splitting path end to
end: create a Gateway, back two model versions with echo servers that return
their version, split traffic with `flint route`, send many requests through
the Gateway, and assert the observed split matches the configured weights.
Then cut over fully and assert no traffic reaches the old version.

Requires (set up by the route-kind CI job): a kind cluster with Envoy Gateway
installed (controller Available in envoy-gateway-system) and kubectl on PATH.

Run:
    FLINT_E2E_ROUTE=1 pytest tests/integration/test_route_kind.py -v
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections import Counter

import httpx
import pytest

_E2E_ENABLED = os.getenv("FLINT_E2E_ROUTE") == "1"
_NS = "flint-route-e2e"
_MODEL = "demo"
_HOST = f"{_MODEL}.local"  # flint route's default hostname
_GATEWAY = "flint-gateway"
_LOCAL_PORT = 18080

_GATEWAY_CLASS = """
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: flint-eg
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
"""

_GATEWAY = f"""
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: {_GATEWAY}
  namespace: {_NS}
spec:
  gatewayClassName: flint-eg
  listeners:
  - name: http
    protocol: HTTP
    port: 80
    allowedRoutes:
      namespaces:
        from: Same
"""


def _backend(version: str) -> str:
    """A tiny echo Deployment+Service named demo-<version> that returns <version>."""
    name = f"{_MODEL}-{version}"
    return f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {_NS}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {_MODEL}
      flint.dev/version: "{version}"
  template:
    metadata:
      labels:
        app: {_MODEL}
        flint.dev/version: "{version}"
    spec:
      containers:
      - name: echo
        image: hashicorp/http-echo:0.2.3
        args: ["-text={version}", "-listen=:80"]
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {_NS}
spec:
  selector:
    app: {_MODEL}
    flint.dev/version: "{version}"
  ports:
  - name: http
    port: 80
    targetPort: 80
"""


def _run(*args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)


def _kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return _run("kubectl", *args)


def _apply(manifest: str) -> None:
    res = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"kubectl apply failed:\n{res.stderr}\n{manifest}"


def _flint_route(*args: str) -> None:
    res = _run("flint", "route", _MODEL, "--namespace", _NS, *args)
    assert res.returncode == 0, f"flint route {args} failed:\n{res.stdout}\n{res.stderr}"


def _envoy_service() -> str:
    """Return the Envoy proxy Service name that fronts our Gateway."""
    res = _kubectl(
        "get", "svc", "-n", "envoy-gateway-system",
        "-l", f"gateway.envoyproxy.io/owning-gateway-name={_GATEWAY}",
        "-o", "jsonpath={.items[0].metadata.name}",
    )
    assert res.returncode == 0 and res.stdout.strip(), (
        f"could not find Envoy proxy service: {res.stderr}"
    )
    return res.stdout.strip()


def _sample(n: int) -> Counter[str]:
    """Send *n* requests through the Gateway and count responses by version."""
    counts: Counter[str] = Counter()
    with httpx.Client(timeout=5.0) as client:
        for _ in range(n):
            resp = client.get(
                f"http://localhost:{_LOCAL_PORT}/", headers={"Host": _HOST}
            )
            counts[resp.text.strip()] += 1
    return counts


@pytest.mark.skipif(not _E2E_ENABLED, reason="FLINT_E2E_ROUTE=1 not set")
def test_route_split_and_cutover() -> None:
    pf: subprocess.Popen[str] | None = None
    try:
        _kubectl("create", "namespace", _NS)
        _apply(_GATEWAY_CLASS)
        _apply(_GATEWAY)
        _apply(_backend("v1"))
        _apply(_backend("v2"))

        # Wait for backends and the Gateway to be ready.
        assert _kubectl(
            "wait", "--for=condition=Available",
            f"deploy/{_MODEL}-v1", f"deploy/{_MODEL}-v2",
            "-n", _NS, "--timeout=180s",
        ).returncode == 0
        assert _kubectl(
            "wait", "--for=condition=Programmed", f"gateway/{_GATEWAY}",
            "-n", _NS, "--timeout=300s",
        ).returncode == 0, _kubectl("describe", "gateway", _GATEWAY, "-n", _NS).stdout

        # Baseline (100% v1), then a 50/50 canary.
        _flint_route("--to", "v1")
        _flint_route("--canary", "50", "v2")

        # Port-forward the Envoy proxy and wait for the route to be live.
        svc = _envoy_service()
        pf = subprocess.Popen(
            ["kubectl", "port-forward", f"svc/{svc}", f"{_LOCAL_PORT}:80",
             "-n", "envoy-gateway-system"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        deadline = time.monotonic() + 60
        live = False
        while time.monotonic() < deadline:
            try:
                r = httpx.get(
                    f"http://localhost:{_LOCAL_PORT}/", headers={"Host": _HOST}, timeout=2.0
                )
                if r.status_code == 200 and r.text.strip() in {"v1", "v2"}:
                    live = True
                    break
            except httpx.RequestError:
                pass
            time.sleep(1)
        assert live, "route did not become live through the Gateway"

        # 50/50 split: both versions should get substantial, roughly even traffic.
        counts = _sample(400)
        assert set(counts) <= {"v1", "v2"}, f"unexpected responses: {counts}"
        v1, v2 = counts.get("v1", 0), counts.get("v2", 0)
        total = v1 + v2
        assert total == 400
        assert 0.35 <= v1 / total <= 0.65, f"split off: v1={v1} v2={v2}"
        assert 0.35 <= v2 / total <= 0.65, f"split off: v1={v1} v2={v2}"

        # --show reflects the split.
        show = _run("flint", "route", _MODEL, "--namespace", _NS, "--show")
        assert "v1: 50%" in show.stdout and "v2: 50%" in show.stdout, show.stdout

        # Full cutover to v2: no v1 traffic afterward.
        _flint_route("--to", "v2")
        time.sleep(3)  # let Envoy pick up the updated HTTPRoute
        after = _sample(100)
        assert after.get("v1", 0) == 0, f"v1 still served after cutover: {after}"
        assert after.get("v2", 0) == 100, f"cutover incomplete: {after}"
    finally:
        if pf is not None and pf.poll() is None:
            pf.send_signal(signal.SIGTERM)
            pf.wait(timeout=10)
        _kubectl("delete", "namespace", _NS, "--ignore-not-found", "--wait=false")
        _kubectl("delete", "gatewayclass", "flint-eg", "--ignore-not-found")
