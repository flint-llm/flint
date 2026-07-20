"""flint version command."""

import importlib.metadata

import click


@click.command()
def version() -> None:
    """Print the installed Flint version."""
    try:
        # Distribution name is "flint-llm" (the import package/command stay "flint").
        v = importlib.metadata.version("flint-llm")
    except importlib.metadata.PackageNotFoundError:
        v = "unknown (package not installed)"
    click.echo(f"flint {v}")
