"""CLI entrypoint — the `flint` command group."""

import click

from flint.cli.init import init
from flint.cli.serve import serve
from flint.cli.version import version


@click.group()
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    envvar="FLINT_DEBUG",
    help="Print full tracebacks on error.",
)
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """Deploy LLMs to Kubernetes."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug


cli.add_command(version)
cli.add_command(init)
cli.add_command(serve)
