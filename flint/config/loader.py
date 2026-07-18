"""Loader for the project's flint.toml configuration file.

flint.toml is optional; commands fall back to built-in defaults and CLI
flags when it is absent. This module reads the file and exposes it as a
typed ``FlintConfig``.

Precedence (CLI flag > flint.toml > built-in default) is resolved by the
CLI, not here. This loader is a faithful reader: it reports what the file
contains, using ``None`` for any key that is absent or blank.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ValidationError

from flint.core.errors import ConfigError

DEFAULT_CONFIG_FILENAME = "flint.toml"


class FlintConfig(BaseModel):
    """Typed view of flint.toml. Every field is optional; None means unset."""

    project_name: str | None = None
    default_runtime: str | None = None
    default_model: str | None = None
    templates_dir: str | None = None


def load_config(path: Path | None = None) -> FlintConfig:
    """Load and parse flint.toml into a typed :class:`FlintConfig`.

    Args:
        path: Path to the config file. Defaults to ``./flint.toml``.

    Returns:
        A :class:`FlintConfig`. When the file does not exist, an all-``None``
        config is returned (flint.toml is optional).

    Raises:
        ConfigError: If the file exists but cannot be read, is not valid TOML,
            has a malformed structure, or contains values of the wrong type.
    """
    config_path = path if path is not None else Path(DEFAULT_CONFIG_FILENAME)

    if not config_path.exists():
        return FlintConfig()

    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read {config_path}: {exc}") from exc

    project = data.get("project", {})
    defaults = data.get("defaults", {})
    templates = data.get("templates", {})
    if not (
        isinstance(project, dict)
        and isinstance(defaults, dict)
        and isinstance(templates, dict)
    ):
        raise ConfigError(
            f"Invalid flint.toml structure in {config_path}: "
            "[project], [defaults], and [templates] must be tables."
        )

    try:
        return FlintConfig(
            project_name=project.get("name") or None,
            default_runtime=defaults.get("runtime") or None,
            default_model=defaults.get("model") or None,
            templates_dir=templates.get("dir") or None,
        )
    except ValidationError as exc:
        raise ConfigError(f"Invalid values in {config_path}: {exc}") from exc
