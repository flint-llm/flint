"""flint logs command — tail a model's runtime pod logs."""

from __future__ import annotations

import click

from flint.cli._errors import handle_flint_error
from flint.core.errors import FlintError
from flint.core.logs import iter_pod_logs
from flint.core.models import normalize_model_name

_DEFAULT_NAMESPACE = "flint"
_UNITS = {"s": 1, "m": 60, "h": 3600}


def _parse_since(value: str | None) -> int | None:
    """Parse a --since duration ('30s', '5m', '1h', or bare seconds) to seconds."""
    if value is None:
        return None
    text = value.strip()
    try:
        if text and text[-1] in _UNITS:
            return int(text[:-1]) * _UNITS[text[-1]]
        return int(text)
    except ValueError as exc:
        raise click.BadParameter(
            f"Invalid --since {value!r}; use e.g. 30s, 5m, 1h, or a number of seconds."
        ) from exc


@click.command("logs")
@click.argument("model")
@click.option("--version", default=None, help="Version to read (default: any).")
@click.option("--follow", "-f", is_flag=True, default=False, help="Stream new log output.")
@click.option("--since", default=None, help="Only logs newer than e.g. 30s, 5m, 1h.")
@click.option("--tail", default=None, type=int, help="Number of recent lines (default: all).")
@click.option("--container", default=None, help="Container name (for multi-container pods).")
@click.option("--namespace", "-n", default=_DEFAULT_NAMESPACE, show_default=True, help="Namespace of the model.")
@click.pass_context
def logs(
    ctx: click.Context,
    model: str,
    version: str | None,
    follow: bool,
    since: str | None,
    tail: int | None,
    container: str | None,
    namespace: str,
) -> None:
    """Tail the runtime pod logs for MODEL."""
    model_name = normalize_model_name(model)
    since_seconds = _parse_since(since)
    try:
        for chunk in iter_pod_logs(
            model_name,
            namespace,
            version=version,
            container=container,
            since_seconds=since_seconds,
            tail_lines=tail,
            follow=follow,
        ):
            click.echo(chunk, nl=False)
    except FlintError as exc:
        handle_flint_error(exc, ctx)
