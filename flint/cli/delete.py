"""flint delete command — remove a model's flint-managed resources."""

from __future__ import annotations

import click

from flint.cli._errors import handle_flint_error
from flint.core.deploy import delete_model
from flint.core.errors import FlintError
from flint.core.models import normalize_model_name

_DEFAULT_NAMESPACE = "flint"


@click.command("delete")
@click.argument("model")
@click.option("--version", default=None, help="Delete only this version (default: all versions).")
@click.option("--namespace", "-n", default=_DEFAULT_NAMESPACE, show_default=True, help="Namespace of the model.")
@click.option("--keep-weights", is_flag=True, default=False, help="Preserve the weights PVC.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip the confirmation prompt.")
@click.pass_context
def delete(
    ctx: click.Context,
    model: str,
    version: str | None,
    namespace: str,
    keep_weights: bool,
    yes: bool,
) -> None:
    """Delete MODEL (Deployment/Service/HPA/PVC + HTTPRoute) from the cluster."""
    model_name = normalize_model_name(model)
    scope = f"{model_name}:{version}" if version else f"{model_name} (all versions)"
    if not yes:
        click.confirm(
            f"Delete {scope} in namespace {namespace!r}?", abort=True
        )

    try:
        deleted = delete_model(
            model_name, namespace, version=version, keep_weights=keep_weights
        )
    except FlintError as exc:
        handle_flint_error(exc, ctx)
        return

    if not deleted:
        click.echo(f"Nothing to delete for {scope} in namespace {namespace!r}.")
        return

    click.echo(f"Deleted {len(deleted)} resource(s):")
    for resource in deleted:
        click.echo(f"  {resource}")
