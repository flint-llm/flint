"""CLI entrypoint — the `flint` command group."""

import click

from flint.cli.delete import delete
from flint.cli.deploy import deploy
from flint.cli.init import init
from flint.cli.list import list_cmd
from flint.cli.route import route
from flint.cli.serve import serve
from flint.cli.status import status
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
cli.add_command(deploy)
cli.add_command(status)
cli.add_command(route)
cli.add_command(list_cmd)
cli.add_command(delete)
