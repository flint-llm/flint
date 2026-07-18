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
from pathlib import Path

from flint.core.build import resolve_runtime_image
from flint.core.cluster import ensure_namespace
from flint.core.errors import TemplateRenderError
from flint.core.k8s_apply import kube_apply, wait_for_rollout
from flint.core.models import (
    DeployResult,
    ModelRef,
    ReadinessProbe,
    RenderContext,
    ResourceSpec,
)
from flint.core.templates import render_deployment_templates

logger = logging.getLogger(__name__)

# Apply order by resource kind. A weights PVC must exist before the Deployment
# that mounts it; the Service and HPA reference the Deployment, so they follow.
_APPLY_ORDER: tuple[str, ...] = ("pvc", "deployment", "service", "hpa")


def build_render_context(
    model: ModelRef,
    runtime: str,
    namespace: str,
    *,
    replicas: int = 1,
    resources: ResourceSpec | None = None,
    readiness_probe: ReadinessProbe | None = None,
    hf_token_secret: str | None = None,
    service_port: int = 8080,
    weights_volume_size: str = "50Gi",
) -> RenderContext:
    """Assemble a :class:`RenderContext` from a model ref and overrides.

    The image is taken from ``model.image`` when set, otherwise resolved from
    *runtime* via :func:`resolve_runtime_image`. HF-Hub weights
    (``model.hf_repo``) flow through so the deployment template mounts the
    weights PVC.
    """
    image = model.image or resolve_runtime_image(runtime)
    return RenderContext(
        model_name=model.name,
        model_version=model.version,
        namespace=namespace,
        runtime=runtime,
        image=image,
        replicas=replicas,
        resources=resources or ResourceSpec(),
        readiness_probe=readiness_probe or ReadinessProbe(),
        hf_repo=model.hf_repo,
        hf_token_secret=hf_token_secret,
        service_port=service_port,
        weights_volume_size=weights_volume_size,
    )


def deploy_model(
    context: RenderContext,
    *,
    output_dir: Path | None = None,
    templates_dir: Path | None = None,
    wait: bool = False,
    wait_timeout_s: int = 600,
) -> DeployResult:
    """Render, apply, and report the endpoint for *context*.

    Steps: ensure namespace -> render manifests -> apply them in dependency
    order (PVC, Deployment, Service, HPA), skipping the PVC unless HF-Hub
    weights are used -> optionally wait for rollout -> compute the in-cluster
    endpoint.

    Args:
        context: The validated render context.
        output_dir: Where to write rendered manifests. A temp dir is used
            when omitted (kept after the call so the applied YAML can be
            inspected).
        templates_dir: Override the built-in templates directory.
        wait: If True, block until the Deployment finishes rolling out.
        wait_timeout_s: Rollout timeout when *wait* is True.

    Raises:
        ClusterError: If the namespace cannot be created.
        TemplateRenderError: If a manifest fails to render, or the runtime has
            no deployable manifests.
        K8sError: If an apply or the rollout wait fails.
    """
    ensure_namespace(context.namespace)

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="flint-deploy-"))
    logger.debug("Rendering manifests into %s", output_dir)

    rendered = render_deployment_templates(
        context, output_dir, runtime=context.runtime, templates_dir=templates_dir
    )
    if not rendered:
        raise TemplateRenderError(
            f"No manifests were rendered for runtime {context.runtime!r}. "
            "Is it a supported deploy runtime (e.g. 'vllm')?"
        )
    ordered = _order_manifests(rendered, include_pvc=context.hf_repo is not None)

    for manifest in ordered:
        kube_apply(manifest, context.namespace)

    name = f"{context.model_name}-{context.model_version}"
    ready = False
    if wait:
        wait_for_rollout(name, context.namespace, timeout_s=wait_timeout_s)
        ready = True

    return DeployResult(
        model_name=context.model_name,
        model_version=context.model_version,
        namespace=context.namespace,
        applied_manifests=ordered,
        endpoint=_in_cluster_endpoint(name, context.namespace),
        ready=ready,
    )


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


def _in_cluster_endpoint(service_name: str, namespace: str) -> str:
    """Return the OpenAI-compatible in-cluster endpoint for the service.

    The Service is ClusterIP on port 80; vLLM exposes its OpenAI API under
    ``/v1``. External routing (Gateway API HTTPRoute) is S5.
    """
    return f"http://{service_name}.{namespace}.svc.cluster.local/v1"
