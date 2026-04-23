"""Tests for flint.core.logs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flint.core.errors import K8sError, ModelNotFoundError
from flint.core.logs import get_deployment_logs, stream_pod_logs


def _fake_pod(name: str = "predict-mistral-v1-abc") -> object:
    return SimpleNamespace(metadata=SimpleNamespace(name=name))


# -- stream_pod_logs ----------------------------------------------------------


def test_stream_pod_logs_pod_not_found_raises() -> None:
    with patch("flint.core.logs.get_pod", return_value=None):
        with pytest.raises(ModelNotFoundError, match="No pod found"):
            stream_pod_logs("missing-service", "flint")


def test_stream_pod_logs_success_no_follow() -> None:
    pod = _fake_pod()
    with (
        patch("flint.core.logs.get_pod", return_value=pod),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        stream_pod_logs("mistral-v1", "flint", follow=False)

    cmd: str = mock_run.call_args[0][0]
    assert "kubectl logs" in cmd
    assert "predict-mistral-v1-abc" in cmd
    assert "-f" not in cmd


def test_stream_pod_logs_success_with_follow() -> None:
    pod = _fake_pod()
    with (
        patch("flint.core.logs.get_pod", return_value=pod),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        stream_pod_logs("mistral-v1", "flint", follow=True)

    cmd: str = mock_run.call_args[0][0]
    assert "-f" in cmd


def test_stream_pod_logs_with_container_name() -> None:
    pod = _fake_pod()
    with (
        patch("flint.core.logs.get_pod", return_value=pod),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        stream_pod_logs("mistral-v1", "flint", container_name="vllm")

    cmd: str = mock_run.call_args[0][0]
    assert "-c vllm" in cmd


def test_stream_pod_logs_kubectl_failure_raises() -> None:
    pod = _fake_pod()
    with (
        patch("flint.core.logs.get_pod", return_value=pod),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(K8sError, match="kubectl logs failed"):
            stream_pod_logs("mistral-v1", "flint")


# -- get_deployment_logs ------------------------------------------------------


def test_get_deployment_logs_calls_stream() -> None:
    with patch("flint.core.logs.stream_pod_logs") as mock_stream:
        get_deployment_logs("mistral", "v1", "flint")

    mock_stream.assert_called_once_with(
        service_name="predict-mistral-v1",
        namespace="flint",
        container_name="predict-mistral",
        follow=True,
    )


def test_get_deployment_logs_custom_registry_ns() -> None:
    with patch("flint.core.logs.stream_pod_logs") as mock_stream:
        get_deployment_logs("mistral", "v1", "flint", image_registry_namespace="serve")

    call_kwargs = mock_stream.call_args[1]
    assert call_kwargs["service_name"] == "serve-mistral-v1"
    assert call_kwargs["container_name"] == "serve-mistral"
