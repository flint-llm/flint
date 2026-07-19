"""Tests for flint.core.routing (Gateway API HTTPRoute; client mocked)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from flint.core.errors import RoutingError
from flint.core.models import TrafficSplit, TrafficWeight
from flint.core.routing import (
    apply_traffic_split,
    build_httproute,
    canary_weights,
    ensure_gateway_api_available,
    get_traffic_split,
    validate_shadow_routes,
)


def _split(**weights: int) -> TrafficSplit:
    return TrafficSplit(
        model_name="llama",
        weights=[TrafficWeight(version=v, weight=w) for v, w in weights.items()],
    )


# -- ensure_gateway_api_available ---------------------------------------------


def test_gateway_available_ok() -> None:
    with patch("flint.core.routing.has_gateway_api", return_value=True):
        ensure_gateway_api_available()  # no raise


def test_gateway_missing_raises_with_install_pointer() -> None:
    with patch("flint.core.routing.has_gateway_api", return_value=False):
        with pytest.raises(RoutingError, match="Envoy Gateway"):
            ensure_gateway_api_available()


# -- build_httproute ----------------------------------------------------------


def test_build_httproute_shape() -> None:
    manifest = build_httproute(
        _split(v1=90, v2=10),
        namespace="flint",
        gateway_name="gw",
        gateway_namespace="infra",
        hostname="llama.local",
    )
    assert manifest["kind"] == "HTTPRoute"
    assert manifest["metadata"]["name"] == "llama"
    spec = manifest["spec"]
    assert spec["parentRefs"] == [{"name": "gw", "namespace": "infra"}]
    assert spec["hostnames"] == ["llama.local"]
    refs = spec["rules"][0]["backendRefs"]
    assert {r["name"]: r["weight"] for r in refs} == {"llama-v1": 90, "llama-v2": 10}
    assert all(r["port"] == 80 for r in refs)


# -- apply_traffic_split ------------------------------------------------------


def test_apply_traffic_split_applies_httproute() -> None:
    with patch("flint.core.routing.kube_apply_manifest") as mock_apply:
        split = apply_traffic_split(
            "llama",
            {"v1": 80, "v2": 20},
            "flint",
            gateway_name="gw",
            gateway_namespace="flint",
            hostname="llama.local",
        )
    assert sum(w.weight for w in split.weights) == 100
    manifest, ns = mock_apply.call_args.args
    assert ns == "flint"
    assert manifest["kind"] == "HTTPRoute"


def test_apply_traffic_split_invalid_weights_raises() -> None:
    with patch("flint.core.routing.kube_apply_manifest") as mock_apply:
        with pytest.raises(RoutingError, match="sum to"):
            apply_traffic_split(
                "m", {"v1": 50}, "flint",
                gateway_name="gw", gateway_namespace="flint", hostname="m.local",
            )
    mock_apply.assert_not_called()


# -- get_traffic_split --------------------------------------------------------


def test_get_traffic_split_parses_backend_weights() -> None:
    obj = {
        "spec": {
            "rules": [
                {
                    "backendRefs": [
                        {"name": "llama-v1", "port": 80, "weight": 70},
                        {"name": "llama-v2", "port": 80, "weight": 30},
                    ]
                }
            ]
        }
    }
    with patch("flint.core.routing.get_resource", return_value=obj):
        split = get_traffic_split("llama", "flint")
    assert split is not None
    assert {w.version: w.weight for w in split.weights} == {"v1": 70, "v2": 30}


def test_get_traffic_split_absent_returns_none() -> None:
    with patch("flint.core.routing.get_resource", return_value=None):
        assert get_traffic_split("llama", "flint") is None


# -- canary_weights (pure) ----------------------------------------------------


def test_canary_weights_from_single_baseline() -> None:
    current = _split(v1=100)
    assert canary_weights(current, "v2", 10) == {"v1": 90, "v2": 10}


def test_canary_weights_adjusts_existing_target() -> None:
    current = _split(v1=90, v2=10)
    assert canary_weights(current, "v2", 25) == {"v1": 75, "v2": 25}


def test_canary_weights_no_baseline_raises() -> None:
    with pytest.raises(RoutingError, match="No baseline"):
        canary_weights(None, "v2", 10)


def test_canary_weights_multiple_baselines_raises() -> None:
    current = _split(v1=50, v3=50)
    with pytest.raises(RoutingError, match="single baseline"):
        canary_weights(current, "v2", 10)


def test_canary_weights_out_of_range_raises() -> None:
    with pytest.raises(RoutingError, match="0-100"):
        canary_weights(_split(v1=100), "v2", 150)


# -- validate_shadow_routes (retained) ----------------------------------------


def test_shadow_valid() -> None:
    validate_shadow_routes({"v1": 100, "v2": 0}, shadow_tags=["v2"])


def test_shadow_tag_non_zero_raises() -> None:
    with pytest.raises(RoutingError, match="must have weight=0"):
        validate_shadow_routes({"v1": 50, "v2": 50}, shadow_tags=["v2"])
