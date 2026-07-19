"""flint deploy command — deploy a model to Kubernetes via a runtime (vLLM).

Resolves configuration with precedence CLI flag > flint.toml > built-in
default, builds a render context, and applies the manifests. External
routing (opening traffic) is a separate step (S5); deploy reports the
in-cluster endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click

from flint.cli._errors import handle_flint_error
from flint.config import load_config
from flint.core.deploy import build_render_context, deploy_model, render_manifests
from flint.core.errors import FlintError
from flint.core.models import ModelRef, ResourceSpec

_DEFAULT_RUNTIME = "vllm"
_DEFAULT_NAMESPACE = "flint"


@click.command("deploy")
@click.argument("model", required=False)
@click.option("--version", "model_version", default=None, help="Model version tag (default: latest).")
@click.option("--runtime", default=None, help=f"Serving runtime (default: {_DEFAULT_RUNTIME}).")
@click.option("--namespace", "-n", default=None, help=f"Target namespace (default: {_DEFAULT_NAMESPACE}).")
@click.option("--replicas", default=1, show_default=True, type=int, help="Number of replicas.")
@click.option("--image", default=None, help="Override the container image (default: runtime's pinned image).")
@click.option("--hf-repo", default=None, help="HuggingFace repo to prefetch weights from.")
@click.option("--hf-token-secret", default=None, help="Name of a k8s Secret holding the HF token (key: token).")
@click.option("--gpu", "gpu_count", default=0, show_default=True, type=int, help="GPUs per replica.")
@click.option("--gpu-type", default="nvidia.com/gpu", show_default=True, help="GPU resource type.")
@click.option("--cpu-request", default=None, help="CPU request (e.g. 500m).")
@click.option("--cpu-limit", default=None, help="CPU limit (e.g. 2000m).")
@click.option("--memory-request", default=None, help="Memory request (e.g. 1Gi).")
@click.option("--memory-limit", default=None, help="Memory limit (e.g. 4Gi).")
@click.option("--service-port", default=None, type=int, help="Container/service target port (default: the runtime's port).")
@click.option("--weights-volume-size", default="50Gi", show_default=True, help="Size of the weights PVC (HF-Hub only).")
@click.option("--weights-access-mode", default="ReadWriteOnce", show_default=True, help="PVC access mode (ReadWriteMany for multi-replica on a supporting StorageClass).")
@click.option("--wait/--no-wait", default=True, show_default=True, help="Wait for the rollout to complete.")
@click.option("--wait-timeout", default=600, show_default=True, type=int, help="Rollout wait timeout in seconds.")
@click.option("--dry-run", is_flag=True, default=False, help="Print the rendered manifests without applying.")
@click.option("--config", "config_path", default=None, type=click.Path(dir_okay=False), help="Path to flint.toml.")
@click.option("--templates-dir", default=None, type=click.Path(file_okay=False), help="Override built-in templates.")
@click.pass_context
def deploy(
    ctx: click.Context,
    model: str | None,
    model_version: str | None,
    runtime: str | None,
    namespace: str | None,
    replicas: int,
    image: str | None,
    hf_repo: str | None,
    hf_token_secret: str | None,
    gpu_count: int,
    gpu_type: str,
    cpu_request: str | None,
    cpu_limit: str | None,
    memory_request: str | None,
    memory_limit: str | None,
    service_port: int | None,
    weights_volume_size: str,
    weights_access_mode: str,
    wait: bool,
    wait_timeout: int,
    dry_run: bool,
    config_path: str | None,
    templates_dir: str | None,
) -> None:
    """Deploy MODEL to Kubernetes.

    MODEL may be omitted when [defaults].model is set in flint.toml.
    """
    try:
        config = load_config(Path(config_path) if config_path else None)

        model_name = model or config.default_model
        if not model_name:
            raise click.UsageError(
                "No model specified. Pass MODEL or set [defaults].model in flint.toml."
            )

        resolved_runtime = runtime or config.default_runtime or _DEFAULT_RUNTIME
        resolved_namespace = namespace or _DEFAULT_NAMESPACE
        resolved_templates = templates_dir or config.templates_dir

        model_ref = ModelRef(
            name=model_name,
            version=model_version or "latest",
            image=image,
            hf_repo=hf_repo,
        )

        cpu_mem = {
            "cpu_request": cpu_request,
            "cpu_limit": cpu_limit,
            "memory_request": memory_request,
            "memory_limit": memory_limit,
        }
        resources = ResourceSpec(
            gpu_count=gpu_count,
            gpu_type=gpu_type,
            **{k: v for k, v in cpu_mem.items() if v is not None},
        )

        context = build_render_context(
            model_ref,
            runtime=resolved_runtime,
            namespace=resolved_namespace,
            replicas=replicas,
            resources=resources,
            hf_token_secret=hf_token_secret,
            service_port=service_port,
            weights_volume_size=weights_volume_size,
            weights_access_mode=weights_access_mode,
        )

        templates_path = Path(resolved_templates) if resolved_templates else None

        if dry_run:
            manifests = render_manifests(context, templates_dir=templates_path)
            for i, manifest in enumerate(manifests):
                if i:
                    click.echo("---")
                click.echo(manifest.read_text(encoding="utf-8").rstrip("\n"))
            return

        result = deploy_model(
            context,
            templates_dir=templates_path,
            wait=wait,
            wait_timeout_s=wait_timeout,
            on_progress=_progress_reporter() if wait else None,
        )
    except FlintError as exc:
        handle_flint_error(exc, ctx)
        return

    click.echo(f"Deployed {result.model_name}:{result.model_version} to namespace {result.namespace}")
    click.echo(f"  manifests applied: {len(result.applied_manifests)}")
    click.echo(f"  endpoint: {result.endpoint}")
    if wait:
        click.echo(f"  rollout: {'ready' if result.ready else 'not ready'}")
    else:
        click.echo("  (rollout not awaited; pass --wait to block until ready)")


def _progress_reporter() -> Callable[[str], None]:
    """Return an on_progress callback that echoes rollout status, deduped."""
    last: dict[str, str] = {}

    def report(msg: str) -> None:
        if last.get("msg") != msg:
            last["msg"] = msg
            click.echo(f"  waiting for rollout: {msg}", err=True)

    return report
