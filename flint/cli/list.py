"""flint list command — list all flint-managed deployments in a namespace."""

from __future__ import annotations

import click

from flint.cli._errors import handle_flint_error
from flint.core.cluster import list_deployments
from flint.core.errors import FlintError

_DEFAULT_NAMESPACE = "flint"


@click.command("list")
@click.option(
    "--namespace",
    "-n",
    default=_DEFAULT_NAMESPACE,
    show_default=True,
    help="Namespace to list.",
)
@click.pass_context
def list_cmd(ctx: click.Context, namespace: str) -> None:
    """List all flint-managed deployments in the namespace."""
    try:
        deployments = list_deployments(namespace)
    except FlintError as exc:
        handle_flint_error(exc, ctx)
        return

    if not deployments:
        click.echo(f"No flint-managed deployments found in namespace {namespace!r}.")
        return

    for d in deployments:
        click.echo(
            f"{d.model_name}:{d.model_version}  "
            f"{d.ready_replicas}/{d.replicas} ready  {d.endpoint}"
        )
