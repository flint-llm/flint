"""Cluster introspection — Gateway API detection, namespace management, endpoints.

Ported from monolith: _get_model_kube_endpoint (3245), _get_all_model_endpoints
(3300), _get_cluster_service (3343), _get_all_nodes (2782),
_get_istio_ingress_nodeport (3287), _get_istio_ingress_ip (3293),
_environment_volumes (3079), has_gateway_api (new — not in monolith).
"""

from __future__ import annotations

import logging
import subprocess
import warnings
from typing import Any

from flint.core.errors import ClusterError
from flint.core.models import DeploymentStatus

logger = logging.getLogger(__name__)


def in_cluster_endpoint(service_name: str, namespace: str) -> str:
    """Return the OpenAI-compatible in-cluster URL for a ClusterIP service.

    The deploy Service is ClusterIP on port 80; vLLM serves its OpenAI API
    under ``/v1``. External routing (Gateway API HTTPRoute) is S5.
    """
    return f"http://{service_name}.{namespace}.svc.cluster.local/v1"


def list_deployments(
    namespace: str, model_name: str | None = None
) -> list[DeploymentStatus]:
    """List flint-managed deployments in *namespace*.

    Selects on the ``flint.dev/managed=true`` label that deploy manifests
    carry, optionally narrowed to a single ``model_name``. Returns each
    deployment's desired/ready replica counts and in-cluster endpoint.

    Raises:
        ClusterError: If the deployments cannot be listed.
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client

    selector = "flint.dev/managed=true"
    if model_name is not None:
        selector += f",flint.dev/model={model_name}"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        apps = k8s_client.AppsV1Api()
        try:
            deployments: list[Any] = apps.list_namespaced_deployment(
                namespace=namespace, label_selector=selector
            ).items
        except Exception as exc:
            raise ClusterError(
                f"Failed to list deployments in {namespace!r}: {exc}"
            ) from exc

    results: list[DeploymentStatus] = []
    for dep in deployments:
        labels: dict[str, str] = dep.metadata.labels or {}
        name = str(dep.metadata.name)
        results.append(
            DeploymentStatus(
                name=name,
                model_name=str(labels.get("flint.dev/model", name)),
                model_version=str(labels.get("flint.dev/version", "")),
                namespace=namespace,
                replicas=int(dep.spec.replicas or 0),
                ready_replicas=int(getattr(dep.status, "ready_replicas", None) or 0),
                endpoint=in_cluster_endpoint(name, namespace),
            )
        )
    return results


def list_nodes() -> list[str]:
    """Return hostnames of all nodes in the cluster.

    Ported from monolith `_get_all_nodes` (lines 2782-2793).
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = k8s_client.CoreV1Api()
        nodes: list[Any] = v1.list_node(watch=False).items

    hostnames: list[str] = []
    for node in nodes:
        labels: dict[str, str] = node.metadata.labels or {}
        hostname = labels.get("kubernetes.io/hostname", str(node.metadata.name))
        hostnames.append(str(hostname))
    return hostnames


def get_model_endpoint(
    model_name: str,
    namespace: str,
    image_registry_namespace: str = "predict",
) -> str | None:
    """Return the HTTP endpoint URL for a deployed model, or None.

    Reads the Ingress resource created during deploy. In S5 this will be
    replaced by a Gateway API HTTPRoute lookup.

    Ported from monolith `_get_model_kube_endpoint` (lines 3245-3284).

    TODO(S5): Replace Ingress lookup with Gateway API HTTPRoute.
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client

    ingress_name = f"{image_registry_namespace}-{model_name}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        networking = k8s_client.NetworkingV1Api()
        try:
            ingress = networking.read_namespaced_ingress(
                name=ingress_name, namespace=namespace
            )
        except Exception as exc:
            raise ClusterError(
                f"Ingress {ingress_name!r} not found in {namespace!r}: {exc}"
            ) from exc

    address = _extract_lb_address(ingress.status)
    if not address:
        try:
            nodeport = _get_ingress_nodeport()
            ip = _get_ingress_ip()
            address = f"{ip}:{nodeport}"
        except ClusterError:
            address = "<ingress-controller-not-found>"

    if not ingress.spec.rules:
        return None
    path: str = str(ingress.spec.rules[0].http.paths[0].path)
    url = f"http://{address}{path}".replace(".*", "invocations")
    return url


def get_all_endpoints(
    namespace: str,
    image_registry_namespace: str = "predict",
) -> list[str]:
    """Return HTTP endpoint URLs for all deployed models in *namespace*.

    Ported from monolith `_get_all_model_endpoints` (lines 3300-3340).
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        networking = k8s_client.NetworkingV1Api()
        ingresses: list[Any] = networking.list_namespaced_ingress(
            namespace=namespace
        ).items

    endpoints: list[str] = []
    for ingress in ingresses:
        address = _extract_lb_address(ingress.status)
        if not address:
            try:
                nodeport = _get_ingress_nodeport()
                ip = _get_ingress_ip()
                address = f"{ip}:{nodeport}"
            except ClusterError:
                address = "<ingress-controller-not-found>"

        if not ingress.spec.rules:
            continue
        path: str = str(ingress.spec.rules[0].http.paths[0].path)
        url = f"http://{address}{path}".replace(".*", "invocations")
        endpoints.append(url)
    return endpoints


def get_service_endpoint(service_name: str, namespace: str) -> str | None:
    """Return the LoadBalancer address for a named service, or None.

    Ported from monolith `_get_cluster_service` (lines 3343-3379).
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = k8s_client.CoreV1Api()
        try:
            svc = v1.read_namespaced_service(
                name=service_name, namespace=namespace
            )
        except Exception as exc:
            raise ClusterError(
                f"Service {service_name!r} not found in {namespace!r}: {exc}"
            ) from exc

    return _extract_lb_address(svc.status)


def has_gateway_api() -> bool:
    """Return True if the Gateway API CRD is installed in the cluster.

    Used by S5 to give an actionable error when Gateway API is missing.
    """
    result = subprocess.run(
        "kubectl get crd httproutes.gateway.networking.k8s.io",
        shell=True,
        capture_output=True,
    )
    return result.returncode == 0


def ensure_namespace(namespace: str) -> None:
    """Create *namespace* if it does not already exist."""
    probe = subprocess.run(
        f"kubectl get namespace {namespace}",
        shell=True,
        capture_output=True,
    )
    if probe.returncode != 0:
        result = subprocess.run(
            f"kubectl create namespace {namespace}",
            shell=True,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ClusterError(
                f"Failed to create namespace {namespace!r}: "
                f"{result.stderr.strip()}"
            )


# -- Private helpers ----------------------------------------------------------


def _load_k8s_config() -> None:
    """Load kubeconfig into the kubernetes Python client."""
    try:
        import kubernetes.config as k8s_config

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            k8s_config.load_kube_config()
    except Exception as exc:
        raise ClusterError(f"Failed to load kubeconfig: {exc}") from exc


def _extract_lb_address(status: Any) -> str | None:
    """Extract hostname or IP from a LoadBalancer status object, or None."""
    try:
        ingress_list: list[Any] = status.load_balancer.ingress or []
        if ingress_list:
            first = ingress_list[0]
            if first.hostname:
                return str(first.hostname)
            if first.ip:
                return str(first.ip)
    except (AttributeError, TypeError):
        pass
    return None


def _get_ingress_nodeport() -> str:
    """Get the NodePort of the cluster ingress controller.

    Ported from monolith `_get_istio_ingress_nodeport` (lines 3287-3290).
    TODO(S5): Replace with Gateway API lookup.
    """
    cmd = (
        "kubectl get svc -n istio-system istio-ingress "
        "-o jsonpath='{.spec.ports[0].nodePort}'"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise ClusterError("Could not determine ingress controller NodePort")
    return result.stdout.strip()


def _get_ingress_ip() -> str:
    """Get the host IP of the ingress controller pod.

    Ported from monolith `_get_istio_ingress_ip` (lines 3293-3296).
    TODO(S5): Replace with Gateway API lookup.
    """
    cmd = (
        "kubectl -n istio-system get po -l istio=ingress "
        "-o jsonpath='{.items[0].status.hostIP}'"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise ClusterError("Could not determine ingress controller IP")
    return result.stdout.strip()
