"""Tests for the flint route command (unit — core mocked)."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from flint.cli.main import cli
from flint.core.errors import RoutingError
from flint.core.models import TrafficSplit, TrafficWeight


def _split(**weights: int) -> TrafficSplit:
    return TrafficSplit(
        model_name="llama",
        weights=[TrafficWeight(version=v, weight=w) for v, w in weights.items()],
    )


def test_route_registered_in_group() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert "route" in result.output


def test_route_requires_exactly_one_action() -> None:
    result = CliRunner().invoke(cli, ["route", "llama"])
    assert result.exit_code != 0
    assert "exactly one" in result.output


def test_route_to_cutover() -> None:
    with (
        patch("flint.cli.route.ensure_gateway_api_available"),
        patch("flint.cli.route.verify_versions_deployed"),
        patch("flint.cli.route.apply_traffic_split", return_value=_split(v2=100)) as mock_apply,
    ):
        result = CliRunner().invoke(cli, ["route", "llama", "--to", "v2"])
    assert result.exit_code == 0, result.output
    weights = mock_apply.call_args.args[1]
    assert weights == {"v2": 100}


def test_route_canary_reads_current_and_rebalances() -> None:
    with (
        patch("flint.cli.route.ensure_gateway_api_available"),
        patch("flint.cli.route.verify_versions_deployed"),
        patch("flint.cli.route.get_traffic_split", return_value=_split(v1=100)),
        patch("flint.cli.route.apply_traffic_split", return_value=_split(v1=90, v2=10)) as mock_apply,
    ):
        result = CliRunner().invoke(cli, ["route", "llama", "--canary", "10", "v2"])
    assert result.exit_code == 0, result.output
    weights = mock_apply.call_args.args[1]
    assert weights == {"v1": 90, "v2": 10}


def test_route_to_undeployed_version_errors() -> None:
    from flint.core.errors import RoutingError

    with (
        patch("flint.cli.route.ensure_gateway_api_available"),
        patch(
            "flint.cli.route.verify_versions_deployed",
            side_effect=RoutingError("Cannot route to undeployed version(s) ['v9']"),
        ),
        patch("flint.cli.route.apply_traffic_split") as mock_apply,
    ):
        result = CliRunner().invoke(cli, ["route", "llama", "--to", "v9"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "undeployed" in result.output
    mock_apply.assert_not_called()


def test_route_show_prints_split() -> None:
    with (
        patch("flint.cli.route.ensure_gateway_api_available"),
        patch("flint.cli.route.get_traffic_split", return_value=_split(v1=70, v2=30)),
    ):
        result = CliRunner().invoke(cli, ["route", "llama", "--show"])
    assert result.exit_code == 0, result.output
    assert "v1: 70%" in result.output
    assert "v2: 30%" in result.output


def test_route_show_no_route() -> None:
    with (
        patch("flint.cli.route.ensure_gateway_api_available"),
        patch("flint.cli.route.get_traffic_split", return_value=None),
    ):
        result = CliRunner().invoke(cli, ["route", "llama", "--show"])
    assert result.exit_code == 0
    assert "No route found" in result.output


def test_route_missing_gateway_api_clean_error() -> None:
    with patch(
        "flint.cli.route.ensure_gateway_api_available",
        side_effect=RoutingError("Gateway API is not installed ... Envoy Gateway"),
    ):
        result = CliRunner().invoke(cli, ["route", "llama", "--to", "v2"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "Gateway API is not installed" in result.output
