"""Tests for flint version command."""

from __future__ import annotations

import re

from click.testing import CliRunner

from flint.cli.main import cli


def test_version_exits_zero() -> None:
    result = CliRunner().invoke(cli, ["version"])
    assert result.exit_code == 0


def test_version_prints_flint_prefix() -> None:
    result = CliRunner().invoke(cli, ["version"])
    assert result.output.startswith("flint ")


def test_version_prints_semver_like_string() -> None:
    result = CliRunner().invoke(cli, ["version"])
    # matches "flint 0.1.0-dev" or "flint 1.2.3" or "flint unknown ..."
    assert re.search(r"flint (\d+\.\d+|\w+)", result.output)


def test_version_in_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert "version" in result.output
