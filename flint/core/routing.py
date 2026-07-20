"""Traffic split management via the Gateway API.

`flint route` splits traffic between deployed model versions by managing a
Gateway API HTTPRoute per model. The HTTPRoute attaches to a pre-existing
Gateway (the cluster/user owns the Gateway and its controller, e.g. Envoy
Gateway) and weights its backendRefs across the per-version Services that
`flint deploy` creates ({model}-{version}).

Ported from monolith: routetraffic (3419), describeroutes (3213),
_validate_and_prep_model_split_tag_and_weight_dict (332). The Istio RouteRules
approach is replaced here by Gateway API HTTPRoute.
"""

from __future__ import annotations

import logging

from flint.core.cluster import has_gateway_api, list_deployments
from flint.core.errors import RoutingError
from flint.core.k8s_apply import get_resource, kube_apply_manifest
from flint.core.models import (
    TrafficSplit,
    TrafficWeight,
    validate_traffic_weights,
)

logger = logging.getLogger(__name__)

_HTTPROUTE_API_VERSION = "gateway.networking.k8s.io/v1"
_HTTPROUTE_KIND = "HTTPRoute"
_BACKEND_PORT = 80


def ensure_gateway_api_available() -> None:
    """Raise RoutingError with install pointers if Gateway API is not installed."""
    if not has_gateway_api():
        raise RoutingError(
            "Gateway API is not installed in this cluster "
            "(CRD httproutes.gateway.networking.k8s.io not found). "
            "Install a Gateway API implementation first, e.g. Envoy Gateway: "
            "https://gateway.envoyproxy.io/docs/install/ — or the Gateway API "
            "CRDs: kubectl apply -f "
            "https://github.com/kubernetes-sigs/gateway-api/releases/latest/"
            "download/standard-install.yaml"
        )


def verify_versions_deployed(
    model_name: str, namespace: str, versions: list[str]
) -> None:
    """Raise RoutingError if any of *versions* has no deployment for the model.

    Guards against routing traffic to a version that was never deployed (e.g.
    a typo in ``--to``/``--canary``), which would send requests to a backend
    that does not exist.
    """
    deployed = {d.model_version for d in list_deployments(namespace, model_name)}
    missing = [v for v in versions if v not in deployed]
    if missing:
        have = ", ".join(sorted(deployed)) or "none"
        raise RoutingError(
            f"Cannot route to undeployed version(s) {sorted(missing)} of "
            f"{model_name!r} (deployed: {have}). Deploy them first."
        )


def apply_traffic_split(
    model_name: str,
    weights: dict[str, int],
    namespace: str,
    *,
    gateway_name: str,
    gateway_namespace: str,
    hostname: str,
) -> TrafficSplit:
    """Validate a split and server-side apply the HTTPRoute for *model_name*.

    Args:
        model_name: The model being routed.
        weights: version tag -> integer percentage (must sum to 100).
        namespace: Namespace of the model's Services and the HTTPRoute.
        gateway_name: Name of the pre-existing Gateway to attach to.
        gateway_namespace: Namespace of that Gateway.
        hostname: Hostname the HTTPRoute matches (e.g. ``mymodel.local``).

    Returns:
        The validated TrafficSplit that was applied.

    Raises:
        RoutingError: If weights are invalid.
        K8sError: If the apply fails.
    """
    try:
        validate_traffic_weights(weights)
    except Exception as exc:
        raise RoutingError(str(exc)) from exc

    split = TrafficSplit(
        model_name=model_name,
        weights=[TrafficWeight(version=tag, weight=int(w)) for tag, w in weights.items()],
    )
    manifest = build_httproute(
        split,
        namespace=namespace,
        gateway_name=gateway_name,
        gateway_namespace=gateway_namespace,
        hostname=hostname,
    )
    kube_apply_manifest(manifest, namespace)
    logger.info(
        "Applied HTTPRoute for %s: %s",
        model_name,
        {tw.version: tw.weight for tw in split.weights},
    )
    return split


def get_traffic_split(model_name: str, namespace: str) -> TrafficSplit | None:
    """Read the current split from the model's HTTPRoute, or None if absent."""
    obj = get_resource(
        _HTTPROUTE_API_VERSION, _HTTPROUTE_KIND, model_name, namespace
    )
    if obj is None:
        return None

    rules = (obj.get("spec") or {}).get("rules") or []
    backend_refs = rules[0].get("backendRefs", []) if rules else []
    prefix = f"{model_name}-"
    weights: list[TrafficWeight] = []
    for ref in backend_refs:
        name = str(ref.get("name", ""))
        version = name[len(prefix):] if name.startswith(prefix) else name
        weights.append(TrafficWeight(version=version, weight=int(ref.get("weight", 0))))
    if not weights:
        return None
    return TrafficSplit(model_name=model_name, weights=weights)


def canary_weights(
    current: TrafficSplit | None, target_version: str, percent: int
) -> dict[str, int]:
    """Compute the weights for shifting *percent* of traffic to *target_version*.

    The remaining ``100 - percent`` stays on the existing baseline version.
    Requires exactly one existing baseline (other than the target); route a
    baseline first with ``--to`` if there is none.

    Raises:
        RoutingError: If *percent* is out of range, or there is no single
            baseline version to canary against.
    """
    if not 0 <= percent <= 100:
        raise RoutingError(f"Canary percent must be 0-100, got {percent}.")

    existing = current.weights if current is not None else []
    baselines = [w.version for w in existing if w.version != target_version and w.weight > 0]
    if not baselines:
        raise RoutingError(
            "No baseline version to canary against. Route a baseline first: "
            "flint route <model> --to <version>."
        )
    if len(baselines) > 1:
        raise RoutingError(
            f"Canary requires a single baseline version; the current split has "
            f"{sorted(baselines)}. Consolidate first with --to <version>."
        )
    return {baselines[0]: 100 - percent, target_version: percent}


def build_httproute(
    split: TrafficSplit,
    *,
    namespace: str,
    gateway_name: str,
    gateway_namespace: str,
    hostname: str,
) -> dict[str, object]:
    """Build the Gateway API HTTPRoute manifest for a validated *split*."""
    backend_refs = [
        {
            "name": f"{split.model_name}-{tw.version}",
            "port": _BACKEND_PORT,
            "weight": tw.weight,
        }
        for tw in split.weights
    ]
    return {
        "apiVersion": _HTTPROUTE_API_VERSION,
        "kind": _HTTPROUTE_KIND,
        "metadata": {
            "name": split.model_name,
            "namespace": namespace,
            "labels": {
                "flint.dev/managed": "true",
                "flint.dev/model": split.model_name,
            },
        },
        "spec": {
            "parentRefs": [{"name": gateway_name, "namespace": gateway_namespace}],
            "hostnames": [hostname],
            "rules": [{"backendRefs": backend_refs}],
        },
    }


def validate_shadow_routes(
    weights: dict[str, int],
    shadow_tags: list[str],
) -> None:
    """Validate that shadow-routed variants have weight=0 in the split.

    Shadow routing itself is a v0.2 feature (Gateway API mirror support is
    uneven); this validation is retained for callers that pre-declare shadows.

    Raises:
        RoutingError: If a shadow tag is missing from *weights* or has weight > 0.
    """
    for tag in shadow_tags:
        if tag not in weights:
            raise RoutingError(
                f"Shadow tag {tag!r} must appear in weights dict with weight=0. "
                f"Got: {weights}"
            )
        if int(weights[tag]) != 0:
            raise RoutingError(
                f"Shadow tag {tag!r} must have weight=0 in the traffic split "
                f"(got {weights[tag]})"
            )
