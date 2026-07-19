"""flint status command — show flint-managed deployments in a namespace."""

from __future__ import annotations

import click

from flint.cli._errors import handle_flint_error
from flint.core.cluster import list_deployments
from flint.core.errors import FlintError
from flint.core.models import normalize_model_name
from flint.core.routing import get_traffic_split

_DEFAULT_NAMESPACE = "flint"


@click.command("status")
@click.argument("model", required=False)
@click.option(
    "--namespace",
    "-n",
    default=_DEFAULT_NAMESPACE,
    show_default=True,
    help="Namespace to inspect.",
)
@click.pass_context
def status(ctx: click.Context, model: str | None, namespace: str) -> None:
    """Show flint-managed deployments, optionally narrowed to MODEL."""
    model_name = normalize_model_name(model) if model else None
    try:
        deployments = list_deployments(namespace, model_name=model_name)
    except FlintError as exc:
        handle_flint_error(exc, ctx)
        return

    if not deployments:
        scope = f" for model {model_name!r}" if model_name else ""
        click.echo(
            f"No flint-managed deployments found in namespace {namespace!r}{scope}."
        )
        return

    for d in deployments:
        ready = f"{d.ready_replicas}/{d.replicas} ready"
        click.echo(f"{d.model_name}:{d.model_version}  {ready}  {d.endpoint}")

    # When narrowed to one model, also show its traffic split (best-effort:
    # there may be no route, or no Gateway API installed).
    if model_name is not None:
        try:
            split = get_traffic_split(model_name, namespace)
        except FlintError:
            split = None
        if split is not None:
            click.echo("traffic split:")
            for tw in split.weights:
                click.echo(f"  {tw.version}: {tw.weight}%")
