"""Pod log retrieval via kubectl.

Ported from monolith: _service_logs (2872), deploy_clusterlogs (2851).

S6 will add --since, --tail, and structured log parsing via the Python
kubernetes client watch API.
"""

from __future__ import annotations

import logging
import subprocess

from flint.core.errors import K8sError, ModelNotFoundError
from flint.core.k8s_apply import get_pod

logger = logging.getLogger(__name__)


def stream_pod_logs(
    service_name: str,
    namespace: str,
    container_name: str | None = None,
    follow: bool = True,
) -> None:
    """Tail logs from the pod matching *service_name*.

    Ported from monolith `_service_logs` (lines 2872-2908).

    Args:
        service_name: Substring used to locate the pod.
        namespace: Kubernetes namespace.
        container_name: Optional container name for multi-container pods.
        follow: If True, follow the log stream (``kubectl logs -f``).

    Raises:
        ModelNotFoundError: If no pod matching *service_name* is found.
        K8sError: If kubectl logs exits non-zero.
    """
    pod = get_pod(service_name, namespace)
    if pod is None:
        raise ModelNotFoundError(
            f"No pod found matching {service_name!r} in namespace {namespace!r}"
        )

    pod_name: str = str(pod.metadata.name)
    follow_flag = "-f" if follow else ""

    if container_name:
        cmd = (
            f"kubectl logs {follow_flag} {pod_name} "
            f"-c {container_name} --namespace={namespace}"
        )
    else:
        cmd = f"kubectl logs {follow_flag} {pod_name} --namespace={namespace}"

    logger.debug("Streaming logs: %s", cmd)
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        raise K8sError(f"kubectl logs failed for pod {pod_name!r}")


def get_deployment_logs(
    model_name: str,
    model_version: str,
    namespace: str,
    image_registry_namespace: str = "predict",
    follow: bool = True,
) -> None:
    """Fetch logs for a deployed model.

    Convenience wrapper over stream_pod_logs.
    Ported from monolith `deploy_clusterlogs` (lines 2851-2869).
    """
    service_name = f"{image_registry_namespace}-{model_name}-{model_version}"
    container_name = f"{image_registry_namespace}-{model_name}"
    stream_pod_logs(
        service_name=service_name,
        namespace=namespace,
        container_name=container_name,
        follow=follow,
    )
