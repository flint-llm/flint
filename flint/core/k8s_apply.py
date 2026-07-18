"""Kubernetes apply, get, delete, scale, and rollout operations.

Write operations (apply, delete, scale) use subprocess kubectl to preserve
the monolith's behaviour. Read operations (get pod, get service) use the
official Python kubernetes client.

TODO(S3): Migrate all write operations to server-side apply via the Python
kubernetes client with field manager "flint".

Ported from monolith: _kube (3176), _kube_apply (3140), _kube_delete (3164),
_get_pod_by_service_name (2731), _get_svc_by_service_name (2752),
_service_scale (3041), _service_stop (3612), _service_rollout (1369).
"""

from __future__ import annotations

import logging
import subprocess
import warnings
from pathlib import Path
from typing import Any

from flint.core.errors import K8sError, ModelNotFoundError

logger = logging.getLogger(__name__)


# -- kubectl write operations -------------------------------------------------


def _run_kubectl(cmd: str) -> None:
    """Run a kubectl command and raise K8sError on failure.

    Ported from monolith `_kube` (lines 3176-3181).
    """
    logger.debug("kubectl: %s", cmd)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise K8sError(
            f"kubectl failed (exit {result.returncode}): {cmd!r}\n"
            f"stderr: {result.stderr.strip()}"
        )


def kube_apply(yaml_path: Path, namespace: str) -> None:
    """Apply a manifest file to the cluster.

    Ported from monolith `_kube_apply` (lines 3140-3150).
    """
    _run_kubectl(f"kubectl apply --namespace {namespace} -f {yaml_path}")


def kube_delete(yaml_path: Path, namespace: str) -> None:
    """Delete resources defined in a manifest file.

    Ported from monolith `_kube_delete` (lines 3164-3173).
    """
    _run_kubectl(f"kubectl delete --namespace {namespace} -f {yaml_path}")


def scale_deployment(deployment_name: str, replicas: int, namespace: str) -> None:
    """Scale a deployment to *replicas* replicas.

    Ported from monolith `_service_scale` (lines 3041-3076).
    """
    _run_kubectl(
        f"kubectl scale deploy {deployment_name} "
        f"--replicas={replicas} --namespace={namespace}"
    )


def delete_deployment(service_name: str, namespace: str) -> None:
    """Delete a deployment whose name contains *service_name*.

    Ported from monolith `_service_stop` (lines 3612-3643).
    """
    pod = get_pod(service_name, namespace)
    if pod is None:
        logger.warning("No pod found matching %r in %s", service_name, namespace)
        return
    deploy_name = _deployment_name_from_pod(pod)
    if not deploy_name:
        raise K8sError(
            f"Cannot determine deployment name for pod {_pod_name(pod)!r}"
        )
    _run_kubectl(f"kubectl delete deploy {deploy_name} --namespace {namespace}")


def rollout_image(
    service_name: str, image: str, tag: str, namespace: str
) -> None:
    """Update a deployment's container image and wait for rollout to complete.

    Ported from monolith `_service_rollout` (lines 1369-1409).
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apps = k8s_client.AppsV1Api()
        items: list[Any] = apps.list_deployment_for_all_namespaces(watch=False).items

    found: Any = None
    for deploy in items:
        if service_name in str(deploy.metadata.name):
            found = deploy
            break

    if found is None:
        raise ModelNotFoundError(
            f"No deployment found matching {service_name!r}"
        )

    deploy_name: str = str(found.metadata.name)
    _run_kubectl(
        f"kubectl set image deploy {deploy_name} {deploy_name}={image}:{tag}"
    )
    _run_kubectl(f"kubectl rollout status deploy {deploy_name}")


# -- kubernetes Python client read operations ---------------------------------


def get_pod(service_name: str, namespace: str) -> Any | None:
    """Return the first pod whose name contains *service_name*, or None.

    Ported from monolith `_get_pod_by_service_name` (lines 2731-2749).
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = k8s_client.CoreV1Api()
        pods: list[Any] = v1.list_pod_for_all_namespaces(watch=False).items

    for pod in pods:
        if service_name in str(pod.metadata.name):
            return pod
    return None


def get_service(service_name: str, namespace: str) -> Any | None:
    """Return the first service whose name contains *service_name*, or None.

    Ported from monolith `_get_svc_by_service_name` (lines 2752-2771).
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = k8s_client.CoreV1Api()
        svcs: list[Any] = v1.list_service_for_all_namespaces(watch=False).items

    for svc in svcs:
        if service_name in str(svc.metadata.name):
            return svc
    return None


# -- Private helpers ----------------------------------------------------------


def _load_k8s_config() -> None:
    """Load kubeconfig into the kubernetes Python client."""
    try:
        import kubernetes.config as k8s_config
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            k8s_config.load_kube_config()
    except Exception as exc:
        raise K8sError(f"Failed to load kubeconfig: {exc}") from exc


def _pod_name(pod: Any) -> str:
    """Extract the name string from a kubernetes Pod object."""
    return str(pod.metadata.name)


def _deployment_name_from_pod(pod: Any) -> str | None:
    """Guess the parent Deployment name from a pod's owner references.

    ReplicaSet name is <deployment>-<hash>; stripping the last segment gives
    the Deployment name.
    """
    refs: list[Any] = pod.metadata.owner_references or []
    for ref in refs:
        if str(ref.kind) == "ReplicaSet":
            parts = str(ref.name).rsplit("-", 1)
            if len(parts) == 2:
                return parts[0]
    return None
