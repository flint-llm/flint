"""Tests for the flint delete command (unit — core mocked)."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from flint.cli.main import cli
from flint.core.errors import K8sError


def test_delete_registered() -> None:
    assert "delete" in CliRunner().invoke(cli, ["--help"]).output


def test_delete_confirms_and_deletes() -> None:
    with patch(
        "flint.cli.delete.delete_model", return_value=["Deployment/demo-v1"]
    ) as mock_delete:
        result = CliRunner().invoke(cli, ["delete", "demo", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Deleted 1 resource" in result.output
    mock_delete.assert_called_once_with("demo", "flint", version=None, keep_weights=False)


def test_delete_aborts_without_confirmation() -> None:
    with patch("flint.cli.delete.delete_model") as mock_delete:
        result = CliRunner().invoke(cli, ["delete", "demo"], input="n\n")
    assert result.exit_code != 0  # click aborts
    mock_delete.assert_not_called()


def test_delete_version_and_keep_weights_forwarded() -> None:
    with patch("flint.cli.delete.delete_model", return_value=[]) as mock_delete:
        CliRunner().invoke(
            cli, ["delete", "demo", "--version", "v1", "--keep-weights", "-y"]
        )
    mock_delete.assert_called_once_with(
        "demo", "flint", version="v1", keep_weights=True
    )


def test_delete_nothing_to_delete() -> None:
    with patch("flint.cli.delete.delete_model", return_value=[]):
        result = CliRunner().invoke(cli, ["delete", "demo", "-y"])
    assert result.exit_code == 0
    assert "Nothing to delete" in result.output


def test_delete_error_no_traceback() -> None:
    with patch("flint.cli.delete.delete_model", side_effect=K8sError("apply failed")):
        result = CliRunner().invoke(cli, ["delete", "demo", "-y"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "apply failed" in result.output
