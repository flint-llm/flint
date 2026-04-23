"""Tests for flint.core.routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from flint.core.errors import RoutingError
from flint.core.routing import (
    apply_traffic_split,
    describe_routes,
    validate_shadow_routes,
)

# -- validate_shadow_routes (pure) --------------------------------------------


def test_shadow_valid() -> None:
    validate_shadow_routes({"v1": 100, "v2": 0}, shadow_tags=["v2"])


def test_shadow_empty_list_valid() -> None:
    validate_shadow_routes({"v1": 100}, shadow_tags=[])


def test_shadow_tag_missing_from_weights_raises() -> None:
    with pytest.raises(RoutingError, match="must appear in weights"):
        validate_shadow_routes({"v1": 100}, shadow_tags=["v2"])


def test_shadow_tag_non_zero_raises() -> None:
    with pytest.raises(RoutingError, match="must have weight=0"):
        validate_shadow_routes({"v1": 50, "v2": 50}, shadow_tags=["v2"])


def test_shadow_multiple_valid() -> None:
    validate_shadow_routes({"v1": 100, "v2": 0, "v3": 0}, shadow_tags=["v2", "v3"])


# -- apply_traffic_split ------------------------------------------------------


def test_apply_traffic_split_valid_returns_split() -> None:
    split = apply_traffic_split("llama", {"v1": 80, "v2": 20}, "flint")
    assert split.model_name == "llama"
    assert len(split.weights) == 2
    total = sum(w.weight for w in split.weights)
    assert total == 100


def test_apply_traffic_split_single_version() -> None:
    split = apply_traffic_split("mistral", {"v1": 100}, "flint")
    assert split.weights[0].version == "v1"
    assert split.weights[0].weight == 100


def test_apply_traffic_split_invalid_weights_raises() -> None:
    with pytest.raises(RoutingError, match="sum to"):
        apply_traffic_split("model", {"v1": 50}, "flint")


def test_apply_traffic_split_zero_total_raises() -> None:
    with pytest.raises(RoutingError):
        apply_traffic_split("model", {}, "flint")


# -- describe_routes ----------------------------------------------------------


def test_describe_routes_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="NAME   CLASS   HOSTS\n", text=True
        )
        result = describe_routes(namespace="flint")
    assert "NAME" in result


def test_describe_routes_kubectl_fails_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not found"
        )
        with pytest.raises(RoutingError, match="Failed to list"):
            describe_routes(namespace="flint")
