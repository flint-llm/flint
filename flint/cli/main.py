"""CLI entrypoint — the `flint` command group."""

from __future__ import annotations

import logging
import traceback

import click

from flint.cli.delete import delete
from flint.cli.deploy import deploy
from flint.cli.init import init
from flint.cli.list import list_cmd
from flint.cli.logs import logs
from flint.cli.route import route
from flint.cli.serve import serve
from flint.cli.status import status
from flint.cli.version import version


class FlintGroup(click.Group):
    """Group that formats *any* uncaught error cleanly unless --debug is set.

    Commands handle expected FlintErrors themselves; this is the safety net so
    no command ever prints a raw Python traceback without --debug.
    """

    def invoke(self, ctx: click.Context) -> object:
        try:
            return super().invoke(ctx)
        except (
            click.ClickException,
            click.exceptions.Abort,
            # click.exceptions.Exit subclasses RuntimeError, so it must be
            # re-raised explicitly or `--help` on a subcommand (which exits
            # this way) would be reported as "Error: 0".
            click.exceptions.Exit,
            SystemExit,
        ):
            raise  # usage errors / aborts / already-handled exits
        except Exception as exc:
            debug = bool((ctx.obj or {}).get("debug"))
            if debug:
                traceback.print_exc()
            click.echo(f"Error: {exc}", err=True)
            ctx.exit(1)


@click.group(cls=FlintGroup)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    envvar="FLINT_DEBUG",
    help="Print full tracebacks on error.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose (INFO) logging.",
)
@click.pass_context
def cli(ctx: click.Context, debug: bool, verbose: bool) -> None:
    """Deploy LLMs to Kubernetes."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


cli.add_command(version)
cli.add_command(init)
cli.add_command(serve)
cli.add_command(deploy)
cli.add_command(status)
cli.add_command(route)
cli.add_command(list_cmd)
cli.add_command(delete)
cli.add_command(logs)
