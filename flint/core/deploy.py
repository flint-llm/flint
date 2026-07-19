"""Deploy orchestration — compose render + apply into `flint deploy`.

Structure ported from the monolith's ``deploy_clusterstart`` (lines
1797-1890): assemble a render context, ensure the namespace, render the
manifest set, apply it in dependency order, then report the in-cluster
endpoint. External routing (Gateway API) is deliberately deferred to S5,
so a deploy lands the Deployment/Service/HPA(/PVC) and reports the
cluster-internal URL; opening external traffic is a separate step.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

from flint.core.cluster import ensure_namespace, in_cluster_endpoint
from flint.core.errors import TemplateRenderError
from flint.core.k8s_apply import delete_by_label, kube_apply, wait_for_rollout
from flint.core.models import (
    DeployResult,
    ModelRef,
    ReadinessProbe,
    RenderContext,
    ResourceSpec,
)
from flint.core.templates import render_deployment_templates
from flint.runtimes import get_adapter

logger = logging.getLogger(__name__)

# Apply order by resource kind. A weights PVC must exist before the Deployment
# that mounts it; the Service and HPA reference the Deployment, so they follow.
_APPLY_ORDER: tuple[str, ...] = ("pvc", "deployment", "service", "hpa")

# Versioned resources deleted per model version (respect --version).
_VERSIONED_KINDS: tuple[tuple[str, str], ...] = (
    ("apps/v1", "Deployment"),
    ("v1", "Service"),
    ("autoscaling/v2", "HorizontalPodAutoscaler"),
)
_HTTPROUTE_API_VERSION = "gateway.networking.k8s.io/v1"


def build_render_context(
    model: ModelRef,
    runtime: str,
    namespace: str,
    *,
    replicas: int = 1,
    resources: ResourceSpec | None = None,
    readiness_probe: ReadinessProbe | None = None,
    hf_token_secret: str | None = None,
    service_port: int | None = None,
    weights_volume_size: str = "50Gi",
    weights_access_mode: str = "ReadWriteOnce",
) -> RenderContext:
    """Assemble a :class:`RenderContext` from a model ref and overrides.

    Runtime-specific defaults (image, port, readiness probe, resources) come
    from the runtime's adapter; any explicit override wins. The image is taken
    from ``model.image`` when set, otherwise the adapter's default. HF-Hub
    weights (``model.hf_repo``) flow through so the deployment template mounts
    the weights PVC.

    The readiness probe's port is forced to the resolved service port: the
    server listens on one port, so the probe must target it (avoids a probe
    that polls a closed port when the port is overridden).

    Raises:
        UnsupportedRuntimeError: If *runtime* has no registered adapter.
    """
    adapter = get_adapter(runtime)
    port = service_port if service_port is not None else adapter.default_service_port()
    readiness = readiness_probe or adapter.default_readiness_probe()
    readiness = readiness.model_copy(update={"port": port})
    return RenderContext(
        model_name=model.name,
        model_version=model.version,
        namespace=namespace,
        runtime=runtime,
        image=model.image or adapter.default_image(),
        replicas=replicas,
        resources=resources or adapter.default_resources(),
        readiness_probe=readiness,
        hf_repo=model.hf_repo,
        hf_token_secret=hf_token_secret,
        service_port=port,
        weights_volume_size=weights_volume_size,
        weights_access_mode=weights_access_mode,
    )


def render_manifests(
    context: RenderContext,
    *,
    output_dir: Path | None = None,
    templates_dir: Path | None = None,
) -> list[Path]:
    """Render the manifest set for *context* into apply order (no cluster calls).

    This is the pure, offline half of a deploy — used both by
    :func:`deploy_model` and by ``flint deploy --dry-run``. Returns the
    rendered manifest paths ordered as they would be applied (PVC before
    Deployment, etc.), with the PVC dropped unless HF-Hub weights are used.

    Raises:
        TemplateRenderError: If a manifest fails to render, or the runtime has
            no deployable manifests.
    """
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="flint-deploy-"))
    logger.debug("Rendering manifests into %s", output_dir)

    adapter = get_adapter(context.runtime)
    rendered = render_deployment_templates(
        context,
        output_dir,
        runtime=adapter.template_subdir,
        templates_dir=templates_dir,
    )
    if not rendered:
        raise TemplateRenderError(
            f"No manifests were rendered for runtime {context.runtime!r} "
            f"(templates: {adapter.template_subdir})."
        )
    return _order_manifests(rendered, include_pvc=context.hf_repo is not None)


def deploy_model(
    context: RenderContext,
    *,
    output_dir: Path | None = None,
    templates_dir: Path | None = None,
    wait: bool = False,
    wait_timeout_s: int = 600,
    on_progress: Callable[[str], None] | None = None,
) -> DeployResult:
    """Render, apply, and report the endpoint for *context*.

    Steps: render manifests -> ensure namespace -> apply them in dependency
    order (PVC, Deployment, Service, HPA), skipping the PVC unless HF-Hub
    weights are used -> optionally wait for rollout -> compute the in-cluster
    endpoint. Rendering happens first so template errors fail fast before any
    cluster mutation.

    Args:
        context: The validated render context.
        output_dir: Where to write rendered manifests. A temp dir is used
            when omitted (kept after the call so the applied YAML can be
            inspected).
        templates_dir: Override the built-in templates directory.
        wait: If True, block until the Deployment finishes rolling out.
        wait_timeout_s: Rollout timeout when *wait* is True.
        on_progress: Optional callback invoked with a short status string each
            rollout poll (only used when *wait* is True).

    Raises:
        ClusterError: If the namespace cannot be created.
        TemplateRenderError: If a manifest fails to render, or the runtime has
            no deployable manifests.
        K8sError: If an apply or the rollout wait fails.
    """
    ordered = render_manifests(
        context, output_dir=output_dir, templates_dir=templates_dir
    )

    ensure_namespace(context.namespace)
    for manifest in ordered:
        kube_apply(manifest, context.namespace)

    name = f"{context.model_name}-{context.model_version}"
    ready = False
    if wait:
        wait_for_rollout(
            name, context.namespace, timeout_s=wait_timeout_s, on_progress=on_progress
        )
        ready = True

    return DeployResult(
        model_name=context.model_name,
        model_version=context.model_version,
        namespace=context.namespace,
        applied_manifests=ordered,
        endpoint=in_cluster_endpoint(name, context.namespace),
        ready=ready,
    )


def delete_model(
    model_name: str,
    namespace: str,
    *,
    version: str | None = None,
    keep_weights: bool = False,
) -> list[str]:
    """Delete a model's flint-managed resources; return what was removed.

    Removes the Deployment/Service/HPA for the model (all versions, or just
    *version* if given). When deleting the whole model (no *version*), also
    removes the weights PVC (unless *keep_weights*) and the HTTPRoute. Matches
    on the ``flint.dev/model`` label, so only flint-managed resources are
    touched. Idempotent — deleting an absent model returns an empty list.

    Raises:
        K8sError: If a delete call fails.
    """
    label = f"flint.dev/model={model_name}"
    versioned = label + (f",flint.dev/version={version}" if version else "")

    deleted: list[str] = []
    for api_version, kind in _VERSIONED_KINDS:
        deleted += delete_by_label(api_version, kind, namespace, versioned)

    if version is None:
        if not keep_weights:
            deleted += delete_by_label(
                "v1", "PersistentVolumeClaim", namespace, label
            )
        # The HTTPRoute only exists if traffic was routed; skip if the Gateway
        # API CRD is not even installed.
        deleted += delete_by_label(
            _HTTPROUTE_API_VERSION, "HTTPRoute", namespace, label,
            ignore_missing_crd=True,
        )
    return deleted


# -- Private helpers ----------------------------------------------------------


def _order_manifests(paths: list[Path], *, include_pvc: bool) -> list[Path]:
    """Sort rendered manifests by apply priority; optionally drop the PVC.

    ``render_deployment_templates`` always renders a PVC, but it is only
    mounted when HF-Hub weights are used, so an unused PVC is not applied.
    Matching is on the filename suffix (``...-<kind>.yaml``) so a model name
    that happens to contain a resource keyword does not misclassify.
    """
    selected = [
        p
        for p in paths
        if include_pvc or not p.name.lower().endswith("pvc.yaml")
    ]
    return sorted(selected, key=_apply_priority)


def _apply_priority(path: Path) -> int:
    name = path.name.lower()
    for i, kind in enumerate(_APPLY_ORDER):
        if name.endswith(f"{kind}.yaml"):
            return i
    return len(_APPLY_ORDER)  # unknown kinds apply last (stable sort)
