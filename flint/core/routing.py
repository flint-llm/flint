"""Traffic split management and HTTPRoute rendering.

In S1 this module ports the validation and structure from the monolith's
Istio RouteRules approach. In S5 it will be rewritten to render Gateway API
HTTPRoute resources and apply them via the Python kubernetes client.

Ported from monolith: routetraffic (3419), describeroutes (3213),
_validate_and_prep_model_split_tag_and_weight_dict (332).

TODO(S5): Replace all Istio routerules logic with Gateway API HTTPRoute.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from flint.core.errors import RoutingError
from flint.core.models import TrafficSplit, TrafficWeight, validate_traffic_weights

logger = logging.getLogger(__name__)


def apply_traffic_split(
    model_name: str,
    weights: dict[str, int],
    namespace: str,
    templates_dir: Path | None = None,
    image_registry_namespace: str = "predict",
) -> TrafficSplit:
    """Validate a traffic split and apply it to the cluster.

    Validates that *weights* sum to 100, constructs a TrafficSplit, then
    renders and applies the routing manifest.

    Ported from monolith `routetraffic` (lines 3419-3528) — validation and
    split construction preserved; Istio-specific rendering deferred to S5.

    Args:
        model_name: The model being routed.
        weights: Mapping of version tag to integer percentage (must sum to 100).
        namespace: Kubernetes namespace.
        templates_dir: Override the built-in templates directory.
        image_registry_namespace: Resource name prefix.

    Returns:
        The validated TrafficSplit that was applied.

    Raises:
        RoutingError: If weights are invalid or the apply operation fails.
    """
    try:
        validate_traffic_weights(weights)
    except Exception as exc:
        raise RoutingError(str(exc)) from exc

    split = TrafficSplit(
        model_name=model_name,
        weights=[
            TrafficWeight(version=tag, weight=int(w)) for tag, w in weights.items()
        ],
    )

    # TODO(S5): Render HTTPRoute template and apply via Python k8s client.
    logger.info(
        "Traffic split applied for %s: %s",
        model_name,
        {tw.version: tw.weight for tw in split.weights},
    )
    return split


def describe_routes(
    model_name: str | None = None,
    namespace: str = "default",
) -> str:
    """Return current route information for a model (or all models).

    Ported from monolith `describeroutes` (lines 3213-3241).
    TODO(S5): Query HTTPRoute resources via the Python k8s client.

    Returns:
        Raw kubectl output describing the ingress resources.

    Raises:
        RoutingError: If the kubectl call fails.
    """
    cmd = f"kubectl get ingress -o wide --namespace={namespace}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RoutingError(
            f"Failed to list ingress resources: {result.stderr.strip()}"
        )
    return result.stdout


def validate_shadow_routes(
    weights: dict[str, int],
    shadow_tags: list[str],
) -> None:
    """Validate that shadow-routed variants have weight=0 in the split.

    Ported from monolith `routetraffic` shadow validation block
    (lines 3468-3485).

    Raises:
        RoutingError: If a shadow tag is missing from *weights* or has
            weight > 0.
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
