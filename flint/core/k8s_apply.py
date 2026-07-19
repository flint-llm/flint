"""Kubernetes apply, get, delete, scale, and rollout operations.

All operations use the official Python kubernetes client. Writes go through
server-side apply (field manager "flint") and typed patch/delete calls; there
is no dependence on the ``kubectl`` binary being on PATH.

Ported from monolith: _kube_apply (3140), _kube_delete (3164),
_get_pod_by_service_name (2731), _get_svc_by_service_name (2752),
_service_scale (3041), _service_stop (3612), _service_rollout (1369).
"""

from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from flint.core.errors import K8sError, ModelNotFoundError

logger = logging.getLogger(__name__)

_FIELD_MANAGER = "flint"
_POLL_INTERVAL_S = 2


# -- write operations (Python client) -----------------------------------------


def kube_apply(yaml_path: Path, namespace: str) -> None:
    """Server-side apply every manifest document in *yaml_path*.

    Uses the dynamic client's server-side apply with field manager "flint"
    and force-conflicts on, so flint owns the fields it manages. Handles
    multi-document manifests.
    """
    docs = _load_manifests(yaml_path)
    client = _dynamic_client()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for doc in docs:
            _server_side_apply(client, doc, namespace, source=yaml_path.name)


def kube_apply_manifest(manifest: dict[str, Any], namespace: str) -> None:
    """Server-side apply a single manifest given as a dict (field manager 'flint').

    Used for resources built in code rather than rendered from a file (e.g.
    the routing HTTPRoute).
    """
    client = _dynamic_client()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _server_side_apply(client, manifest, namespace, source=str(manifest.get("kind")))


def get_resource(
    api_version: str, kind: str, name: str, namespace: str
) -> dict[str, Any] | None:
    """Return a namespaced resource as a plain dict, or None if it does not exist."""
    from kubernetes.dynamic.exceptions import NotFoundError

    client = _dynamic_client()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            resource = client.resources.get(api_version=api_version, kind=kind)
            obj = client.get(resource, name=name, namespace=namespace)
        except NotFoundError:
            return None
        except Exception as exc:
            raise K8sError(
                f"Failed to get {kind} {name!r} in {namespace}: {exc}"
            ) from exc
    return dict(obj.to_dict())


def kube_delete(yaml_path: Path, namespace: str) -> None:
    """Delete every resource defined in *yaml_path*.

    Missing resources (already deleted) are ignored, matching the intent of
    ``kubectl delete --ignore-not-found``. Handles multi-document manifests.
    """
    from kubernetes.dynamic.exceptions import NotFoundError

    docs = _load_manifests(yaml_path)
    client = _dynamic_client()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for doc in docs:
            kind = str(doc.get("kind", "<unknown>"))
            name = doc.get("metadata", {}).get("name")
            try:
                resource = client.resources.get(
                    api_version=doc["apiVersion"], kind=doc["kind"]
                )
                client.delete(resource, name=name, namespace=namespace)
            except NotFoundError:
                logger.debug("%s %r already absent in %s", kind, name, namespace)
            except Exception as exc:
                raise K8sError(
                    f"Failed to delete {kind} {name!r} from {yaml_path.name}: {exc}"
                ) from exc


def delete_by_label(
    api_version: str,
    kind: str,
    namespace: str,
    label_selector: str,
    *,
    ignore_missing_crd: bool = False,
) -> list[str]:
    """Delete all *kind* resources matching *label_selector*; return their names.

    Returns the ``"{kind}/{name}"`` of each deleted resource (empty if none
    matched). When *ignore_missing_crd* is True, a missing resource kind (e.g.
    HTTPRoute when the Gateway API is not installed) is silently skipped.
    """
    from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError

    client = _dynamic_client()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            resource = client.resources.get(api_version=api_version, kind=kind)
        except ResourceNotFoundError as exc:
            if ignore_missing_crd:
                return []
            raise K8sError(
                f"Resource kind {kind!r} ({api_version}) not found"
            ) from exc
        try:
            listing = client.get(
                resource, namespace=namespace, label_selector=label_selector
            )
            names = [str(item.metadata.name) for item in listing.items]
            if names:
                client.delete(
                    resource, namespace=namespace, label_selector=label_selector
                )
        except NotFoundError:
            return []
        except Exception as exc:
            raise K8sError(
                f"Failed to delete {kind} by label {label_selector!r} "
                f"in {namespace}: {exc}"
            ) from exc
    return [f"{kind}/{n}" for n in names]


def scale_deployment(deployment_name: str, replicas: int, namespace: str) -> None:
    """Scale a deployment to *replicas* replicas via the scale subresource."""
    _load_k8s_config()
    import kubernetes.client as k8s_client

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apps = k8s_client.AppsV1Api()
        try:
            apps.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=namespace,
                body={"spec": {"replicas": replicas}},
            )
        except Exception as exc:
            raise K8sError(
                f"Failed to scale deployment {deployment_name!r} "
                f"to {replicas} in {namespace}: {exc}"
            ) from exc


def delete_deployment(service_name: str, namespace: str) -> None:
    """Delete the deployment backing the pod whose name contains *service_name*."""
    pod = get_pod(service_name, namespace)
    if pod is None:
        logger.warning("No pod found matching %r in %s", service_name, namespace)
        return
    deploy_name = _deployment_name_from_pod(pod)
    if not deploy_name:
        raise K8sError(
            f"Cannot determine deployment name for pod {_pod_name(pod)!r}"
        )

    _load_k8s_config()
    import kubernetes.client as k8s_client

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apps = k8s_client.AppsV1Api()
        try:
            apps.delete_namespaced_deployment(name=deploy_name, namespace=namespace)
        except Exception as exc:
            raise K8sError(
                f"Failed to delete deployment {deploy_name!r} in {namespace}: {exc}"
            ) from exc


def rollout_image(
    service_name: str, image: str, tag: str, namespace: str
) -> None:
    """Update a deployment's container image and wait for rollout to complete."""
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
        raise ModelNotFoundError(f"No deployment found matching {service_name!r}")

    deploy_name = str(found.metadata.name)
    deploy_ns = str(found.metadata.namespace)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apps = k8s_client.AppsV1Api()
        try:
            apps.patch_namespaced_deployment(
                name=deploy_name,
                namespace=deploy_ns,
                body={
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {"name": deploy_name, "image": f"{image}:{tag}"}
                                ]
                            }
                        }
                    }
                },
            )
        except Exception as exc:
            raise K8sError(
                f"Failed to set image on deployment {deploy_name!r}: {exc}"
            ) from exc

    wait_for_rollout(deploy_name, deploy_ns)


def wait_for_rollout(
    deployment_name: str,
    namespace: str,
    timeout_s: int = 600,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Block until *deployment_name* finishes rolling out.

    Polls the deployment status until the observed generation has caught up
    and updated/ready/available replicas all meet the spec. Raises K8sError
    if that does not happen within *timeout_s* seconds. When *on_progress* is
    given, it is called each poll with a short human-readable status string.
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client

    deadline = time.monotonic() + timeout_s
    while True:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            apps = k8s_client.AppsV1Api()
            try:
                dep = apps.read_namespaced_deployment(deployment_name, namespace)
            except Exception as exc:
                raise K8sError(
                    f"Failed to read deployment {deployment_name!r} "
                    f"in {namespace}: {exc}"
                ) from exc

        ready = int(getattr(dep.status, "ready_replicas", 0) or 0)
        want = int(dep.spec.replicas or 0)
        if on_progress is not None:
            on_progress(f"{ready}/{want} replicas ready")

        if _rollout_complete(dep):
            return
        if time.monotonic() >= deadline:
            raise K8sError(
                f"Deployment {deployment_name!r} did not complete rollout within "
                f"{timeout_s}s (ready {ready}/{want})"
            )
        time.sleep(_POLL_INTERVAL_S)


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


def _load_manifests(yaml_path: Path) -> list[dict[str, Any]]:
    """Parse all YAML documents in *yaml_path* into a list of dicts."""
    try:
        docs = list(yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        raise K8sError(f"Failed to read manifest {yaml_path}: {exc}") from exc
    return [d for d in docs if isinstance(d, dict)]


def _server_side_apply(
    client: Any, doc: dict[str, Any], namespace: str, source: str
) -> None:
    """Server-side apply one manifest *doc*. Must run inside catch_warnings."""
    kind = str(doc.get("kind", "<unknown>"))
    try:
        resource = client.resources.get(
            api_version=doc["apiVersion"], kind=doc["kind"]
        )
        client.server_side_apply(
            resource,
            body=doc,
            namespace=namespace,
            field_manager=_FIELD_MANAGER,
            force_conflicts=True,
        )
    except Exception as exc:
        raise K8sError(f"Failed to apply {kind} from {source}: {exc}") from exc


def _dynamic_client() -> Any:
    """Load kubeconfig and return a dynamic client for server-side apply."""
    _load_k8s_config()
    import kubernetes.client as k8s_client
    from kubernetes import dynamic
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return dynamic.DynamicClient(k8s_client.ApiClient())


def _rollout_complete(dep: Any) -> bool:
    """Return True if *dep*'s status shows the current spec fully rolled out."""
    spec_replicas = int(dep.spec.replicas or 0)
    status = dep.status
    generation = int(dep.metadata.generation or 0)
    observed = int(getattr(status, "observed_generation", 0) or 0)
    updated = int(getattr(status, "updated_replicas", 0) or 0)
    ready = int(getattr(status, "ready_replicas", 0) or 0)
    available = int(getattr(status, "available_replicas", 0) or 0)
    return (
        observed >= generation
        and updated >= spec_replicas
        and ready >= spec_replicas
        and available >= spec_replicas
    )


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
