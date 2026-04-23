"""flint serve command — local mode via Ollama."""

import sys

import click

# Implemented fully in Phase 4; stub here so Phase 1 imports succeed.


@click.command("serve")
@click.argument("model")
@click.option(
    "--port",
    default=11434,
    show_default=True,
    help="Port for the Ollama server.",
)
@click.pass_context
def serve(ctx: click.Context, model: str, port: int) -> None:
    """Serve MODEL locally via Ollama (OpenAI-compatible endpoint)."""
    # Implemented in Phase 4.
    click.echo("flint serve: not yet implemented", err=True)
    sys.exit(1)
