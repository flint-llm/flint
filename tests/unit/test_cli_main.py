"""Tests for the flint group's top-level error handling (FlintGroup)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from flint.cli.main import cli


def test_unexpected_error_is_formatted_not_raw() -> None:
    # A non-FlintError escaping a command must be caught and formatted, not
    # surfaced as a raw traceback (exit criteria 2/4).
    with patch("flint.cli.list.list_deployments", side_effect=ValueError("kaboom")):
        result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "kaboom" in result.output


def test_help_lists_all_commands() -> None:
    out = CliRunner().invoke(cli, ["--help"]).output
    for cmd in ("deploy", "status", "route", "list", "delete", "logs", "serve"):
        assert cmd in out


@pytest.mark.parametrize(
    "command",
    ["deploy", "status", "list", "logs", "delete", "route", "serve", "init", "version"],
)
def test_subcommand_help_exits_cleanly(command: str) -> None:
    # click.exceptions.Exit subclasses RuntimeError; if FlintGroup swallowed it,
    # `flint <cmd> --help` would print "Error: 0" and exit 1.
    result = CliRunner().invoke(cli, [command, "--help"])
    assert result.exit_code == 0
    assert "Error" not in result.output
    assert f"Usage: cli {command}" in result.output
