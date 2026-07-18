"""Tests for flint.core.k8s_apply."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flint.core.errors import K8sError
from flint.core.k8s_apply import (
    _deployment_name_from_pod,
    _pod_name,
    _run_kubectl,
    delete_deployment,
    get_pod,
    get_service,
    kube_apply,
    kube_delete,
    scale_deployment,
)

# -- _pod_name ----------------------------------------------------------------


def test_pod_name_returns_string() -> None:
    pod = SimpleNamespace(metadata=SimpleNamespace(name="my-pod-abc"))
    assert _pod_name(pod) == "my-pod-abc"


# -- _deployment_name_from_pod ------------------------------------------------


def test_deployment_name_from_replicaset_ref() -> None:
    ref = SimpleNamespace(kind="ReplicaSet", name="my-deploy-5f9d8")
    pod = SimpleNamespace(metadata=SimpleNamespace(owner_references=[ref]))
    assert _deployment_name_from_pod(pod) == "my-deploy"


def test_deployment_name_no_replicaset_ref() -> None:
    ref = SimpleNamespace(kind="DaemonSet", name="my-ds-abc")
    pod = SimpleNamespace(metadata=SimpleNamespace(owner_references=[ref]))
    assert _deployment_name_from_pod(pod) is None


def test_deployment_name_no_refs() -> None:
    pod = SimpleNamespace(metadata=SimpleNamespace(owner_references=[]))
    assert _deployment_name_from_pod(pod) is None


def test_deployment_name_none_refs() -> None:
    pod = SimpleNamespace(metadata=SimpleNamespace(owner_references=None))
    assert _deployment_name_from_pod(pod) is None


# -- _run_kubectl -------------------------------------------------------------


def test_run_kubectl_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        _run_kubectl("kubectl version")
    mock_run.assert_called_once()


def test_run_kubectl_failure_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="error message")
        with pytest.raises(K8sError, match="kubectl failed"):
            _run_kubectl("kubectl bad-command")


# -- kube_apply ---------------------------------------------------------------


def test_kube_apply_calls_kubectl() -> None:
    with patch("flint.core.k8s_apply._run_kubectl") as mock_run:
        kube_apply(Path("/tmp/manifest.yaml"), "flint")
    mock_run.assert_called_once()
    cmd: str = mock_run.call_args[0][0]
    assert "kubectl apply" in cmd
    assert "--namespace flint" in cmd
    assert "manifest.yaml" in cmd


# -- kube_delete --------------------------------------------------------------


def test_kube_delete_calls_kubectl() -> None:
    with patch("flint.core.k8s_apply._run_kubectl") as mock_run:
        kube_delete(Path("/tmp/manifest.yaml"), "flint")
    mock_run.assert_called_once()
    cmd: str = mock_run.call_args[0][0]
    assert "kubectl delete" in cmd
    assert "--namespace flint" in cmd
    assert "manifest.yaml" in cmd


# -- scale_deployment ---------------------------------------------------------


def test_scale_deployment_calls_kubectl() -> None:
    with patch("flint.core.k8s_apply._run_kubectl") as mock_run:
        scale_deployment("my-deploy", 3, "flint")
    mock_run.assert_called_once_with(
        "kubectl scale deploy my-deploy --replicas=3 --namespace=flint"
    )


# -- get_pod / get_service (mocked k8s client) --------------------------------


def _make_k8s_mock(pod_name: str) -> MagicMock:
    pod = SimpleNamespace(metadata=SimpleNamespace(name=pod_name))
    response = MagicMock()
    response.items = [pod]
    return response


def test_get_pod_found() -> None:
    mock_response = _make_k8s_mock("predict-mistral-v1-abc123")
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.list_pod_for_all_namespaces.return_value = mock_response
        mock_api_cls.return_value = mock_api

        result = get_pod("mistral-v1", "flint")
    assert result is not None
    assert result.metadata.name == "predict-mistral-v1-abc123"


def test_get_pod_not_found() -> None:
    mock_response = _make_k8s_mock("some-other-pod")
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.list_pod_for_all_namespaces.return_value = mock_response
        mock_api_cls.return_value = mock_api

        result = get_pod("mistral-v1", "flint")
    assert result is None


def test_get_service_found() -> None:
    svc = SimpleNamespace(metadata=SimpleNamespace(name="predict-mistral-v1"))
    response = MagicMock()
    response.items = [svc]
    with (
        patch("flint.core.k8s_apply._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api") as mock_api_cls,
    ):
        mock_api = MagicMock()
        mock_api.list_service_for_all_namespaces.return_value = response
        mock_api_cls.return_value = mock_api

        result = get_service("mistral-v1", "flint")
    assert result is not None


# -- delete_deployment --------------------------------------------------------


def test_delete_deployment_no_pod_warns(caplog: pytest.LogCaptureFixture) -> None:
    with (
        patch("flint.core.k8s_apply.get_pod", return_value=None),
        patch("flint.core.k8s_apply._run_kubectl") as mock_run,
    ):
        delete_deployment("mistral-v1", "flint")
    mock_run.assert_not_called()


def test_delete_deployment_with_pod() -> None:
    ref = SimpleNamespace(kind="ReplicaSet", name="mistral-v1-abc-xyz")
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="mistral-v1-pod", owner_references=[ref])
    )
    with (
        patch("flint.core.k8s_apply.get_pod", return_value=pod),
        patch("flint.core.k8s_apply._run_kubectl") as mock_run,
    ):
        delete_deployment("mistral-v1", "flint")
    mock_run.assert_called_once_with(
        "kubectl delete deploy mistral-v1-abc --namespace flint"
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
