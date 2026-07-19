"""flint route command — manage traffic splits between model versions.

Manages a Gateway API HTTPRoute per model, attached to a pre-existing Gateway.
Three modes (exactly one per invocation):

  flint route MODEL --to VERSION            # cut all traffic to VERSION
  flint route MODEL --canary PCT VERSION    # shift PCT% to VERSION (canary)
  flint route MODEL --show                  # print the current split
"""

from __future__ import annotations

import click

from flint.cli._errors import handle_flint_error
from flint.core.errors import FlintError
from flint.core.models import normalize_model_name
from flint.core.routing import (
    apply_traffic_split,
    canary_weights,
    ensure_gateway_api_available,
    get_traffic_split,
)

_DEFAULT_NAMESPACE = "flint"
_DEFAULT_GATEWAY = "flint-gateway"


@click.command("route")
@click.argument("model")
@click.option(
    "--canary",
    nargs=2,
    type=(int, str),
    default=None,
    metavar="PCT VERSION",
    help="Shift PCT%% of traffic to VERSION (baseline keeps the rest).",
)
@click.option("--to", "cutover", default=None, metavar="VERSION", help="Cut all traffic to VERSION.")
@click.option("--show", is_flag=True, default=False, help="Show the current split.")
@click.option("--gateway", default=_DEFAULT_GATEWAY, show_default=True, help="Name of the Gateway to attach to.")
@click.option("--gateway-namespace", default=None, help="Gateway namespace (default: --namespace).")
@click.option("--host", default=None, help="Hostname the route matches (default: <model>.local).")
@click.option("--namespace", "-n", default=_DEFAULT_NAMESPACE, show_default=True, help="Namespace of the model.")
@click.pass_context
def route(
    ctx: click.Context,
    model: str,
    canary: tuple[int, str] | None,
    cutover: str | None,
    show: bool,
    gateway: str,
    gateway_namespace: str | None,
    host: str | None,
    namespace: str,
) -> None:
    """Manage traffic splits for MODEL across its deployed versions."""
    actions = [canary is not None, cutover is not None, show]
    if sum(actions) != 1:
        raise click.UsageError(
            "Specify exactly one of --canary, --to, or --show."
        )

    model_name = normalize_model_name(model)
    try:
        ensure_gateway_api_available()

        if show:
            split = get_traffic_split(model_name, namespace)
            if split is None:
                click.echo(f"No route found for {model_name!r} in namespace {namespace!r}.")
                return
            click.echo(f"Traffic split for {model_name}:")
            for tw in split.weights:
                click.echo(f"  {tw.version}: {tw.weight}%")
            return

        if cutover is not None:
            weights = {normalize_model_name(cutover): 100}
        else:
            assert canary is not None
            pct, target = canary
            current = get_traffic_split(model_name, namespace)
            weights = canary_weights(current, normalize_model_name(target), pct)

        hostname = host or f"{model_name}.local"
        split = apply_traffic_split(
            model_name,
            weights,
            namespace,
            gateway_name=gateway,
            gateway_namespace=gateway_namespace or namespace,
            hostname=hostname,
        )
    except FlintError as exc:
        handle_flint_error(exc, ctx)
        return

    click.echo(f"Routed {model_name} (host {hostname}):")
    for tw in split.weights:
        click.echo(f"  {tw.version}: {tw.weight}%")
