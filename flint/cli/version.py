"""flint version command."""

import importlib.metadata

import click


@click.command()
def version() -> None:
    """Print the installed Flint version."""
    try:
        v = importlib.metadata.version("flint")
    except importlib.metadata.PackageNotFoundError:
        v = "unknown (package not installed)"
    click.echo(f"flint {v}")
