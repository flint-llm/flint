"""Tests for the flint logs command (unit — core mocked)."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from flint.cli.main import cli
from flint.core.errors import ModelNotFoundError


def test_logs_registered() -> None:
    assert "logs" in CliRunner().invoke(cli, ["--help"]).output


def test_logs_prints_output() -> None:
    with patch("flint.cli.logs.iter_pod_logs", return_value=iter(["hello\n", "world\n"])):
        result = CliRunner().invoke(cli, ["logs", "demo"])
    assert result.exit_code == 0, result.output
    assert "hello" in result.output
    assert "world" in result.output


def test_logs_since_and_tail_forwarded() -> None:
    with patch("flint.cli.logs.iter_pod_logs", return_value=iter([])) as mock_iter:
        CliRunner().invoke(cli, ["logs", "demo", "--since", "5m", "--tail", "50"])
    assert mock_iter.call_args.kwargs["since_seconds"] == 300
    assert mock_iter.call_args.kwargs["tail_lines"] == 50


def test_logs_bad_since_rejected() -> None:
    result = CliRunner().invoke(cli, ["logs", "demo", "--since", "abc"])
    assert result.exit_code != 0
    assert "Invalid --since" in result.output


def test_logs_error_no_traceback() -> None:
    with patch("flint.cli.logs.iter_pod_logs", side_effect=ModelNotFoundError("no pods")):
        result = CliRunner().invoke(cli, ["logs", "demo"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "no pods" in result.output
