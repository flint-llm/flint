"""Tests for flint.core.k8s_apply (Python-client writes; client mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flint.core.errors import K8sError, ModelNotFoundError
from flint.core.k8s_apply import (
    _deployment_name_from_pod,
    _pod_name,
    _rollout_complete,
    delete_deployment,
    get_pod,
    get_service,
    kube_apply,
    kube_delete,
    rollout_image,
    scale_deployment,
    wait_for_rollout,
)


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(text, encoding="utf-8")
    return p


_DEPLOYMENT = "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: demo\n"
_MULTI = (
    "apiVersion: v1\nkind: Service\nmetadata:\n  name: s\n"
    "---\n"
    "apiVersion: autoscaling/v2\nkind: HorizontalPodAutoscaler\nmetadata:\n  name: h\n"
)


# -- _pod_name / _deployment_name_from_pod ------------------------------------


def test_pod_name_returns_string() -> None:
    pod = SimpleNamespace(metadata=SimpleNamespace(name="my-pod-abc"))
    assert _pod_name(pod) == "my-pod-abc"


def test_deployment_name_from_replicaset_ref() -> None:
    ref = SimpleNamespace(kind="ReplicaSet", name="my-deploy-5f9d8")
    pod = SimpleNamespace(metadata=SimpleNamespace(owner_references=[ref]))
    assert _deployment_name_from_pod(pod) == "my-deploy"


def test_deployment_name_no_replicaset_ref() -> None:
    ref = SimpleNamespace(kind="DaemonSet", name="my-ds-abc")
    pod = SimpleNamespace(metadata=SimpleNamespace(owner_references=[ref]))
    assert _deployment_name_from_pod(pod) is None


def test_deployment_name_none_refs() -> None:
    pod = SimpleNamespace(metadata=SimpleNamespace(owner_references=None))
    assert _deployment_name_from_pod(pod) is None


# -- kube_apply (server-side apply) -------------------------------------------


def test_kube_apply_server_side_applies(tmp_path: Path) -> None:
    manifest = _write(tmp_path, _DEPLOYMENT)
    client = MagicMock()
    with patch("flint.core.k8s_apply._dynamic_client", return_value=client):
        kube_apply(manifest, "flint")
    client.resources.get.assert_called_once_with(
        api_version="apps/v1", kind="Deployment"
    )
    call = client.server_side_apply.call_args
    assert call.args[0] is client.resources.get.return_value  # the resource
    assert call.kwargs["namespace"] == "flint"
    assert call.kwargs["field_manager"] == "flint"
    assert call.kwargs["force_conflicts"] is True
    assert call.kwargs["body"]["kind"] == "Deployment"


def test_kube_apply_multi_document(tmp_path: Path) -> None:
    manifest = _write(tmp_path, _MULTI)
    client = MagicMock()
    with patch("flint.core.k8s_apply._dynamic_client", return_value=client):
        kube_apply(manifest, "flint")
    assert client.server_side_apply.call_count == 2
    kinds = {c.kwargs["body"]["kind"] for c in client.server_side_apply.call_args_list}
    assert kinds == {"Service", "HorizontalPodAutoscaler"}


def test_kube_apply_error_wrapped(tmp_path: Path) -> None:
    manifest = _write(tmp_path, _DEPLOYMENT)
    client = MagicMock()
    client.server_side_apply.side_effect = RuntimeError("boom")
    with patch("flint.core.k8s_apply._dynamic_client", return_value=client):
        with pytest.raises(K8sError, match="Failed to apply Deployment"):
            kube_apply(manifest, "flint")


# -- kube_delete --------------------------------------------------------------


def test_kube_delete_deletes_by_name(tmp_path: Path) -> None:
    manifest = _write(tmp_path, _DEPLOYMENT)
    client = MagicMock()
    with patch("flint.core.k8s_apply._dynamic_client", return_value=client):
        kube_delete(manifest, "flint")
    call = client.delete.call_args
    assert call.kwargs["name"] == "demo"
    assert call.kwargs["namespace"] == "flint"


def test_kube_delete_ignores_not_found(tmp_path: Path) -> None:
    from kubernetes.client.exceptions import ApiException
    from kubernetes.dynamic.exceptions import NotFoundError

    manifest = _write(tmp_path, _DEPLOYMENT)
    client = MagicMock()
    client.delete.side_effect = NotFoundError(ApiException(status=404))
    with patch("flint.core.k8s_apply._dynamic_client", return_value=client):
        kube_delete(manifest, "flint")  # must not raise


def test_kube_delete_error_wrapped(tmp_path: Path) -> None:
    manifest = _write(tmp_path, _DEPLOYMENT)
    client = MagicMock()
    client.delete.side_effect = RuntimeError("boom")
    with patch("flint.core.k8s_apply._dynamic_client", return_value=client):
        with pytest.raises(K8sError, match="Failed to delete Deployment"):
            kube_delete(manifest, "flint")


# -- scale_deployment ---------------------------------------------------------


def test_scale_deployment_patches_scale() -> None:
    mock_api = MagicMock()
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        scale_deployment("demo", 3, "flint")
    call = mock_api.patch_namespaced_deployment_scale.call_args
    assert call.kwargs["name"] == "demo"
    assert call.kwargs["namespace"] == "flint"
    assert call.kwargs["body"] == {"spec": {"replicas": 3}}


def test_scale_deployment_error_wrapped() -> None:
    mock_api = MagicMock()
    mock_api.patch_namespaced_deployment_scale.side_effect = RuntimeError("boom")
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        with pytest.raises(K8sError, match="Failed to scale"):
            scale_deployment("demo", 3, "flint")


# -- delete_deployment --------------------------------------------------------


def test_delete_deployment_no_pod_warns() -> None:
    mock_api = MagicMock()
    with (
        patch("flint.core.k8s_apply.get_pod", return_value=None),
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        delete_deployment("mistral-v1", "flint")
    mock_api.delete_namespaced_deployment.assert_not_called()


def test_delete_deployment_with_pod() -> None:
    ref = SimpleNamespace(kind="ReplicaSet", name="mistral-v1-abc-xyz")
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="mistral-v1-pod", owner_references=[ref])
    )
    mock_api = MagicMock()
    with (
        patch("flint.core.k8s_apply.get_pod", return_value=pod),
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        delete_deployment("mistral-v1", "flint")
    mock_api.delete_namespaced_deployment.assert_called_once_with(
        name="mistral-v1-abc", namespace="flint"
    )


def test_delete_deployment_no_replicaset_raises() -> None:
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="pod-name", owner_references=[])
    )
    with (
        patch("flint.core.k8s_apply.get_pod", return_value=pod),
        pytest.raises(K8sError, match="Cannot determine deployment name"),
    ):
        delete_deployment("mistral-v1", "flint")


# -- rollout_image ------------------------------------------------------------


def test_rollout_image_patches_and_waits() -> None:
    dep = SimpleNamespace(metadata=SimpleNamespace(name="demo-v1", namespace="flint"))
    listing = MagicMock()
    listing.items = [dep]
    mock_api = MagicMock()
    mock_api.list_deployment_for_all_namespaces.return_value = listing
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
        patch("flint.core.k8s_apply.wait_for_rollout") as mock_wait,
    ):
        rollout_image("demo", "my/img", "v2", "flint")
    call = mock_api.patch_namespaced_deployment.call_args
    assert call.kwargs["name"] == "demo-v1"
    container = call.kwargs["body"]["spec"]["template"]["spec"]["containers"][0]
    assert container == {"name": "demo-v1", "image": "my/img:v2"}
    mock_wait.assert_called_once_with("demo-v1", "flint")


def test_rollout_image_not_found_raises() -> None:
    listing = MagicMock()
    listing.items = []
    mock_api = MagicMock()
    mock_api.list_deployment_for_all_namespaces.return_value = listing
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        with pytest.raises(ModelNotFoundError, match="No deployment found"):
            rollout_image("missing", "img", "v1", "flint")


# -- wait_for_rollout / _rollout_complete -------------------------------------


def _dep(spec: int, gen: int, obs: int, upd: int, ready: int, avail: int) -> object:
    return SimpleNamespace(
        spec=SimpleNamespace(replicas=spec),
        metadata=SimpleNamespace(generation=gen),
        status=SimpleNamespace(
            observed_generation=obs,
            updated_replicas=upd,
            ready_replicas=ready,
            available_replicas=avail,
        ),
    )


def test_rollout_complete_true_when_all_meet_spec() -> None:
    assert _rollout_complete(_dep(2, 3, 3, 2, 2, 2)) is True


def test_rollout_complete_false_when_not_ready() -> None:
    assert _rollout_complete(_dep(2, 3, 3, 2, 1, 2)) is False


def test_rollout_complete_false_when_generation_not_observed() -> None:
    assert _rollout_complete(_dep(1, 5, 4, 1, 1, 1)) is False


def test_wait_for_rollout_returns_when_complete() -> None:
    mock_api = MagicMock()
    mock_api.read_namespaced_deployment.return_value = _dep(2, 3, 3, 2, 2, 2)
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
    ):
        wait_for_rollout("demo", "flint", timeout_s=5)  # returns immediately


def test_wait_for_rollout_times_out() -> None:
    mock_api = MagicMock()
    mock_api.read_namespaced_deployment.return_value = _dep(2, 3, 3, 1, 1, 1)
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.AppsV1Api", return_value=mock_api),
        patch("time.monotonic", side_effect=[0.0, 100.0]),
        patch("time.sleep"),
    ):
        with pytest.raises(K8sError, match="did not complete rollout"):
            wait_for_rollout("demo", "flint", timeout_s=5)


# -- get_pod / get_service ----------------------------------------------------


def test_get_pod_found() -> None:
    pod = SimpleNamespace(metadata=SimpleNamespace(name="predict-mistral-v1-abc"))
    response = MagicMock()
    response.items = [pod]
    mock_api = MagicMock()
    mock_api.list_pod_for_all_namespaces.return_value = response
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=mock_api),
    ):
        result = get_pod("mistral-v1", "flint")
    assert result is not None
    assert result.metadata.name == "predict-mistral-v1-abc"


def test_get_pod_not_found() -> None:
    pod = SimpleNamespace(metadata=SimpleNamespace(name="some-other-pod"))
    response = MagicMock()
    response.items = [pod]
    mock_api = MagicMock()
    mock_api.list_pod_for_all_namespaces.return_value = response
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=mock_api),
    ):
        result = get_pod("mistral-v1", "flint")
    assert result is None


def test_get_service_found() -> None:
    svc = SimpleNamespace(metadata=SimpleNamespace(name="predict-mistral-v1"))
    response = MagicMock()
    response.items = [svc]
    mock_api = MagicMock()
    mock_api.list_service_for_all_namespaces.return_value = response
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=mock_api),
    ):
        result = get_service("mistral-v1", "flint")
    assert result is not None
