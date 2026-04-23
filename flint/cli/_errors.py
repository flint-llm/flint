"""CLI error formatting utilities.

Converts FlintError subclasses into clean one-line messages. When --debug
is set on the parent group, full tracebacks are printed instead.
"""

from __future__ import annotations

import sys
import traceback

import click

from flint.core.errors import FlintError


def exit_with_error(
    message: str,
    debug: bool = False,
    exc: BaseException | None = None,
) -> None:
    """Print an error message and exit 1. Print traceback if debug is set."""
    if debug and exc is not None:
        traceback.print_exc()
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def get_debug(ctx: click.Context | None) -> bool:
    """Extract the --debug flag from the Click context object."""
    if ctx is None or ctx.obj is None:
        return False
    return bool(ctx.obj.get("debug", False))


def handle_flint_error(exc: FlintError, ctx: click.Context | None = None) -> None:
    """Format a FlintError and exit 1. Respects --debug."""
    debug = get_debug(ctx)
    exit_with_error(str(exc), debug=debug, exc=exc)
