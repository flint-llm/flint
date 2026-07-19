"""Tests for the flint status command (unit — cluster mocked)."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from flint.cli.main import cli
from flint.core.errors import ClusterError
from flint.core.models import DeploymentStatus


def _dep(**kw: object) -> DeploymentStatus:
    base: dict[str, object] = {
        "name": "m-v1",
        "model_name": "m",
        "model_version": "v1",
        "namespace": "flint",
        "replicas": 2,
        "ready_replicas": 1,
        "endpoint": "http://m-v1.flint.svc.cluster.local/v1",
    }
    base.update(kw)
    return DeploymentStatus(**base)  # type: ignore[arg-type]


def test_status_lists_deployments() -> None:
    with patch("flint.cli.status.list_deployments", return_value=[_dep()]) as mock_list:
        result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 0, result.output
    assert "m:v1" in result.output
    assert "1/2 ready" in result.output
    assert "svc.cluster.local/v1" in result.output
    mock_list.assert_called_once_with("flint", model_name=None)


def test_status_empty_message() -> None:
    with patch("flint.cli.status.list_deployments", return_value=[]):
        result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "No flint-managed deployments" in result.output


def test_status_model_filter_normalized() -> None:
    with patch("flint.cli.status.list_deployments", return_value=[]) as mock_list:
        CliRunner().invoke(cli, ["status", "Mistral", "-n", "prod"])
    mock_list.assert_called_once_with("prod", model_name="mistral")


def test_status_error_handled_no_traceback() -> None:
    with patch("flint.cli.status.list_deployments", side_effect=ClusterError("boom")):
        result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "boom" in result.output


def test_status_registered_in_group() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert "status" in result.output


def test_status_model_shows_traffic_split() -> None:
    from flint.core.models import TrafficSplit, TrafficWeight

    split = TrafficSplit(
        model_name="m",
        weights=[TrafficWeight(version="v1", weight=70), TrafficWeight(version="v2", weight=30)],
    )
    with (
        patch("flint.cli.status.list_deployments", return_value=[_dep()]),
        patch("flint.cli.status.get_traffic_split", return_value=split),
    ):
        result = CliRunner().invoke(cli, ["status", "m"])
    assert result.exit_code == 0, result.output
    assert "traffic split" in result.output
    assert "v1: 70%" in result.output


def test_status_no_route_omits_split() -> None:
    with (
        patch("flint.cli.status.list_deployments", return_value=[_dep()]),
        patch("flint.cli.status.get_traffic_split", return_value=None),
    ):
        result = CliRunner().invoke(cli, ["status", "m"])
    assert result.exit_code == 0
    assert "traffic split" not in result.output
