"""Tests for flint.core.cluster."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flint.core.cluster import (
    _extract_lb_address,
    _get_ingress_ip,
    _get_ingress_nodeport,
    ensure_namespace,
    get_all_endpoints,
    get_model_endpoint,
    get_service_endpoint,
    has_gateway_api,
    in_cluster_endpoint,
    list_deployments,
    list_nodes,
)
from flint.core.errors import ClusterError

# -- _extract_lb_address (pure) -----------------------------------------------


def _lb_status(hostname: str | None = None, ip: str | None = None) -> object:
    entry = SimpleNamespace(hostname=hostname, ip=ip)
    lb = SimpleNamespace(ingress=[entry])
    return SimpleNamespace(load_balancer=lb)


def test_extract_lb_hostname() -> None:
    status = _lb_status(hostname="my-lb.example.com")
    assert _extract_lb_address(status) == "my-lb.example.com"


def test_extract_lb_ip() -> None:
    status = _lb_status(ip="1.2.3.4")
    assert _extract_lb_address(status) == "1.2.3.4"


def test_extract_lb_hostname_takes_priority() -> None:
    status = _lb_status(hostname="host.example.com", ip="1.2.3.4")
    assert _extract_lb_address(status) == "host.example.com"


def test_extract_lb_empty_list() -> None:
    status = SimpleNamespace(load_balancer=SimpleNamespace(ingress=[]))
    assert _extract_lb_address(status) is None


def test_extract_lb_none_status() -> None:
    assert _extract_lb_address(None) is None


def test_extract_lb_attribute_error() -> None:
    assert _extract_lb_address(SimpleNamespace()) is None


# -- has_gateway_api ----------------------------------------------------------


def test_has_gateway_api_true() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert has_gateway_api() is True


def test_has_gateway_api_false() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert has_gateway_api() is False


# -- ensure_namespace ---------------------------------------------------------


def test_ensure_namespace_exists_skips() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ensure_namespace("flint")
    mock_run.assert_called_once()


def test_ensure_namespace_missing_creates() -> None:
    responses = [
        MagicMock(returncode=1),
        MagicMock(returncode=0, stderr=""),
    ]
    with patch("subprocess.run", side_effect=responses):
        ensure_namespace("new-ns")


def test_ensure_namespace_create_fails_raises() -> None:
    responses = [
        MagicMock(returncode=1),
        MagicMock(returncode=1, stderr="forbidden"),
    ]
    with patch("subprocess.run", side_effect=responses):
        with pytest.raises(ClusterError, match="Failed to create namespace"):
            ensure_namespace("bad-ns")


# -- _get_ingress_nodeport ----------------------------------------------------


def test_get_ingress_nodeport_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="30080", text=True)
        result = _get_ingress_nodeport()
    assert result == "30080"


def test_get_ingress_nodeport_failure_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with pytest.raises(ClusterError, match="NodePort"):
            _get_ingress_nodeport()


# -- _get_ingress_ip ----------------------------------------------------------


def test_get_ingress_ip_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="192.168.1.1")
        result = _get_ingress_ip()
    assert result == "192.168.1.1"


def test_get_ingress_ip_failure_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with pytest.raises(ClusterError, match="IP"):
            _get_ingress_ip()


# -- list_nodes ---------------------------------------------------------------


def _make_node(hostname: str) -> object:
    labels = {"kubernetes.io/hostname": hostname}
    return SimpleNamespace(metadata=SimpleNamespace(labels=labels, name=hostname))


def test_list_nodes_returns_hostnames() -> None:
    nodes = [_make_node("node-1"), _make_node("node-2")]
    response = MagicMock()
    response.items = nodes
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.list_node.return_value = response
        mock_cls.return_value = mock_api
        result = list_nodes()
    assert result == ["node-1", "node-2"]


def test_list_nodes_empty_cluster() -> None:
    response = MagicMock()
    response.items = []
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.list_node.return_value = response
        mock_cls.return_value = mock_api
        result = list_nodes()
    assert result == []


# -- get_service_endpoint -----------------------------------------------------


def _make_svc_status(ip: str) -> object:
    lb_entry = SimpleNamespace(ip=ip, hostname=None)
    lb = SimpleNamespace(ingress=[lb_entry])
    return SimpleNamespace(load_balancer=lb)


def test_get_service_endpoint_found() -> None:
    svc = SimpleNamespace(status=_make_svc_status("10.0.0.1"))
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.read_namespaced_service.return_value = svc
        mock_cls.return_value = mock_api
        result = get_service_endpoint("my-svc", "flint")
    assert result == "10.0.0.1"


def test_get_service_endpoint_not_found_raises() -> None:
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.read_namespaced_service.side_effect = Exception("not found")
        mock_cls.return_value = mock_api
        with pytest.raises(ClusterError, match="not found"):
            get_service_endpoint("missing", "flint")


# -- get_all_endpoints --------------------------------------------------------


def _make_ingress(path: str, ip: str) -> object:
    lb_entry = SimpleNamespace(ip=ip, hostname=None)
    lb = SimpleNamespace(ingress=[lb_entry])
    status = SimpleNamespace(load_balancer=lb)
    path_item = SimpleNamespace(path=path)
    http = SimpleNamespace(paths=[path_item])
    rule = SimpleNamespace(http=http)
    spec = SimpleNamespace(rules=[rule])
    return SimpleNamespace(status=status, spec=spec)


def test_get_all_endpoints_returns_list() -> None:
    ingress = _make_ingress("/predict/mistral/", "1.2.3.4")
    response = MagicMock()
    response.items = [ingress]
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.NetworkingV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.list_namespaced_ingress.return_value = response
        mock_cls.return_value = mock_api
        result = get_all_endpoints("flint")
    assert len(result) == 1
    assert "1.2.3.4" in result[0]


def test_get_all_endpoints_empty() -> None:
    response = MagicMock()
    response.items = []
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.NetworkingV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.list_namespaced_ingress.return_value = response
        mock_cls.return_value = mock_api
        result = get_all_endpoints("flint")
    assert result == []


# -- get_model_endpoint -------------------------------------------------------


def test_get_model_endpoint_found() -> None:
    ingress = _make_ingress("/predict/mistral/", "1.2.3.4")
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.NetworkingV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.read_namespaced_ingress.return_value = ingress
        mock_cls.return_value = mock_api
        result = get_model_endpoint("mistral", "flint")
    assert result is not None
    assert "1.2.3.4" in result


def test_get_model_endpoint_not_found_raises() -> None:
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.NetworkingV1Api") as mock_cls,
    ):
        mock_api = MagicMock()
        mock_api.read_namespaced_ingress.side_effect = Exception("not found")
        mock_cls.return_value = mock_api
        with pytest.raises(ClusterError, match="not found"):
            get_model_endpoint("missing", "flint")


# -- in_cluster_endpoint ------------------------------------------------------


def test_in_cluster_endpoint_format() -> None:
    assert (
        in_cluster_endpoint("m-v1", "flint")
        == "http://m-v1.flint.svc.cluster.local/v1"
    )


# -- list_deployments ---------------------------------------------------------


def _make_deployment(
    name: str, model: str, version: str, replicas: int | None, ready: int | None
) -> object:
    labels = {
        "flint.dev/managed": "true",
        "flint.dev/model": model,
        "flint.dev/version": version,
    }
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, labels=labels),
        spec=SimpleNamespace(replicas=replicas),
        status=SimpleNamespace(ready_replicas=ready),
    )


def _patch_apps(items: list[object]) -> tuple[object, object]:
    response = MagicMock()
    response.items = items
    mock_api = MagicMock()
    mock_api.list_namespaced_deployment.return_value = response
    return mock_api, response


def test_list_deployments_parses_status() -> None:
    mock_api, _ = _patch_apps([_make_deployment("m-v1", "m", "v1", 2, 1)])
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        result = list_deployments("flint")
    assert len(result) == 1
    d = result[0]
    assert d.model_name == "m"
    assert d.model_version == "v1"
    assert d.replicas == 2
    assert d.ready_replicas == 1
    assert d.endpoint == "http://m-v1.flint.svc.cluster.local/v1"
    kwargs = mock_api.list_namespaced_deployment.call_args.kwargs
    assert kwargs["namespace"] == "flint"
    assert kwargs["label_selector"] == "flint.dev/managed=true"


def test_list_deployments_model_filter_selector() -> None:
    mock_api, _ = _patch_apps([])
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        list_deployments("prod", model_name="mistral")
    kwargs = mock_api.list_namespaced_deployment.call_args.kwargs
    assert kwargs["label_selector"] == "flint.dev/managed=true,flint.dev/model=mistral"


def test_list_deployments_ready_replicas_none_is_zero() -> None:
    mock_api, _ = _patch_apps([_make_deployment("m-v1", "m", "v1", 1, None)])
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        result = list_deployments("flint")
    assert result[0].ready_replicas == 0
    assert result[0].replicas == 1


def test_list_deployments_api_error_raises() -> None:
    mock_api = MagicMock()
    mock_api.list_namespaced_deployment.side_effect = RuntimeError("boom")
    with (
        patch("flint.core.cluster._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        with pytest.raises(ClusterError, match="Failed to list deployments"):
            list_deployments("flint")
