"""Tests for the flint list command (unit — cluster mocked)."""

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


def test_list_registered() -> None:
    assert "list" in CliRunner().invoke(cli, ["--help"]).output


def test_list_shows_deployments() -> None:
    with patch("flint.cli.list.list_deployments", return_value=[_dep()]) as mock_list:
        result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code == 0, result.output
    assert "m:v1" in result.output
    assert "1/2 ready" in result.output
    mock_list.assert_called_once_with("flint")


def test_list_empty() -> None:
    with patch("flint.cli.list.list_deployments", return_value=[]):
        result = CliRunner().invoke(cli, ["list", "-n", "prod"])
    assert result.exit_code == 0
    assert "No flint-managed deployments" in result.output


def test_list_error_no_traceback() -> None:
    with patch("flint.cli.list.list_deployments", side_effect=ClusterError("boom")):
        result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "boom" in result.output
