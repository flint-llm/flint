"""flint init command."""

from pathlib import Path

import click

_TOML_TEMPLATE = """\
[project]
name = "{name}"

[defaults]
runtime = "ollama"
model = ""

[templates]
# dir = "./flint-templates"   # uncomment to override built-in templates
"""


@click.command("init")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite an existing flint.toml.",
)
def init(force: bool) -> None:
    """Scaffold a flint.toml in the current directory."""
    target = Path("flint.toml")

    if target.exists() and not force:
        click.echo(
            "Error: flint.toml already exists. Use --force to overwrite.", err=True
        )
        raise SystemExit(1)

    name = Path.cwd().name
    content = _TOML_TEMPLATE.format(name=name)
    target.write_text(content, encoding="utf-8")
    click.echo(f"Created flint.toml (project: {name})")
