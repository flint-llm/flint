"""Tests for flint init command."""

from __future__ import annotations

import tomllib
from pathlib import Path

from click.testing import CliRunner

from flint.cli.main import cli


def _invoke_init(*args: str) -> object:
    return CliRunner().invoke(cli, ["init", *args])


def test_init_creates_flint_toml() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert Path("flint.toml").exists()


def test_init_toml_is_valid() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(cli, ["init"])
        with open("flint.toml", "rb") as f:
            config = tomllib.load(f)
        assert "project" in config
        assert "defaults" in config
        assert "templates" in config


def test_init_toml_has_expected_keys() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(cli, ["init"])
        with open("flint.toml", "rb") as f:
            config = tomllib.load(f)
        assert config["defaults"]["runtime"] == "ollama"
        assert "model" in config["defaults"]
        assert "name" in config["project"]


def test_init_refuses_overwrite_without_force() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("flint.toml").write_text("existing = true", encoding="utf-8")
        result = runner.invoke(cli, ["init"])
        assert result.exit_code != 0
        # Original file not touched
        assert Path("flint.toml").read_text() == "existing = true"


def test_init_force_overwrites() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("flint.toml").write_text("existing = true", encoding="utf-8")
        result = runner.invoke(cli, ["init", "--force"])
        assert result.exit_code == 0
        with open("flint.toml", "rb") as f:
            config = tomllib.load(f)
        # Should be a valid flint.toml, not "existing = true"
        assert "project" in config


def test_init_project_name_from_directory() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=None):
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        with open("flint.toml", "rb") as f:
            config = tomllib.load(f)
        # Name should be a non-empty string (derived from cwd)
        assert isinstance(config["project"]["name"], str)
        assert len(config["project"]["name"]) > 0


def test_init_success_message() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init"])
        assert "Created flint.toml" in result.output
