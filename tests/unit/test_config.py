"""Tests for flint.config.loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from flint.config import FlintConfig, load_config
from flint.core.errors import ConfigError

_FULL_TOML = """\
[project]
name = "my-project"

[defaults]
runtime = "vllm"
model = "mistral"

[templates]
dir = "./flint-templates"
"""

# What `flint init` scaffolds: model is an empty string, templates.dir commented out.
_SCAFFOLD_TOML = """\
[project]
name = "scaffolded"

[defaults]
runtime = "ollama"
model = ""

[templates]
# dir = "./flint-templates"
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "flint.toml"
    p.write_text(content, encoding="utf-8")
    return p


# -- missing file -------------------------------------------------------------


def test_missing_file_returns_all_none(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "does-not-exist.toml")
    assert cfg == FlintConfig()
    assert cfg.project_name is None
    assert cfg.default_runtime is None
    assert cfg.default_model is None
    assert cfg.templates_dir is None


def test_default_path_when_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No flint.toml in cwd -> all-None config, no error.
    monkeypatch.chdir(tmp_path)
    assert load_config() == FlintConfig()


# -- full config --------------------------------------------------------------


def test_loads_full_config(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    assert cfg.project_name == "my-project"
    assert cfg.default_runtime == "vllm"
    assert cfg.default_model == "mistral"
    assert cfg.templates_dir == "./flint-templates"


def test_default_path_is_flint_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, _FULL_TOML)
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.project_name == "my-project"


# -- scaffold (blanks -> None) ------------------------------------------------


def test_scaffold_blank_model_becomes_none(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _SCAFFOLD_TOML))
    assert cfg.project_name == "scaffolded"
    assert cfg.default_runtime == "ollama"
    assert cfg.default_model is None  # empty string normalized to None
    assert cfg.templates_dir is None  # commented out


def test_missing_sections_are_none(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, '[project]\nname = "solo"\n'))
    assert cfg.project_name == "solo"
    assert cfg.default_runtime is None
    assert cfg.templates_dir is None


# -- errors -------------------------------------------------------------------


def test_malformed_toml_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Invalid TOML"):
        load_config(_write(tmp_path, "this is = = not valid toml ["))


def test_non_table_section_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="must be tables"):
        load_config(_write(tmp_path, 'project = "not-a-table"\n'))


def test_wrong_value_type_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Invalid values"):
        load_config(_write(tmp_path, "[project]\nname = 123\n"))
