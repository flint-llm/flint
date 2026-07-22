"""Tests for flint.core.logs (Python client; mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flint.core.errors import K8sError, ModelNotFoundError
from flint.core.logs import find_model_pod, iter_pod_logs


def _pod(name: str, phase: str = "Running") -> object:
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name), status=SimpleNamespace(phase=phase)
    )


def _core(pods: list[object]) -> MagicMock:
    api = MagicMock()
    api.list_namespaced_pod.return_value = SimpleNamespace(items=pods)
    return api


# -- find_model_pod -----------------------------------------------------------


def test_find_model_pod_prefers_running() -> None:
    api = _core([_pod("m-v1-a", "Pending"), _pod("m-v1-b", "Running")])
    with (
        patch("flint.core.logs._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=api),
    ):
        assert find_model_pod("m", "flint") == "m-v1-b"
    assert api.list_namespaced_pod.call_args.kwargs["label_selector"] == "flint.dev/model=m"


def test_find_model_pod_version_selector() -> None:
    api = _core([_pod("m-v1-a")])
    with (
        patch("flint.core.logs._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=api),
    ):
        find_model_pod("m", "flint", version="v1")
    assert (
        api.list_namespaced_pod.call_args.kwargs["label_selector"]
        == "flint.dev/model=m,flint.dev/version=v1"
    )


def test_find_model_pod_none_raises() -> None:
    api = _core([])
    with (
        patch("flint.core.logs._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=api),
    ):
        with pytest.raises(ModelNotFoundError, match="No pods found"):
            find_model_pod("m", "flint")


# -- iter_pod_logs ------------------------------------------------------------


def _raw_response(data: bytes) -> MagicMock:
    """A non-preloaded urllib3 response, as the client returns for logs."""
    resp = MagicMock()
    resp.data = data
    return resp


def test_iter_pod_logs_non_follow_yields_text() -> None:
    api = _core([_pod("m-v1-a")])
    api.read_namespaced_pod_log.return_value = _raw_response(b"line1\nline2\n")
    with (
        patch("flint.core.logs._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=api),
    ):
        out = list(iter_pod_logs("m", "flint", tail_lines=10))
    assert out == ["line1\nline2\n"]
    call = api.read_namespaced_pod_log.call_args
    assert call.kwargs["tail_lines"] == 10
    assert call.kwargs["name"] == "m-v1-a"


def test_iter_pod_logs_non_follow_bypasses_deserialization() -> None:
    # The client's deserialize() coerces a plain-text body with str(bytes),
    # yielding a b'...\n...' repr. _preload_content=False avoids that path;
    # 0.1.0 shipped without it and printed the repr to users.
    api = _core([_pod("m-v1-a")])
    api.read_namespaced_pod_log.return_value = _raw_response(b"hello\nworld\n")
    with (
        patch("flint.core.logs._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=api),
    ):
        out = list(iter_pod_logs("m", "flint"))
    assert api.read_namespaced_pod_log.call_args.kwargs["_preload_content"] is False
    assert out == ["hello\nworld\n"]
    assert not out[0].startswith("b'") and "\\n" not in out[0]
    api.read_namespaced_pod_log.return_value.release_conn.assert_called_once()


def test_iter_pod_logs_follow_streams_chunks() -> None:
    api = _core([_pod("m-v1-a")])
    resp = MagicMock()
    resp.stream.return_value = [b"chunk1", b"chunk2"]
    api.read_namespaced_pod_log.return_value = resp
    with (
        patch("flint.core.logs._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=api),
    ):
        out = list(iter_pod_logs("m", "flint", follow=True))
    assert out == ["chunk1", "chunk2"]
    resp.release_conn.assert_called_once()
    assert api.read_namespaced_pod_log.call_args.kwargs["follow"] is True


def test_iter_pod_logs_read_error_wrapped() -> None:
    api = _core([_pod("m-v1-a")])
    api.read_namespaced_pod_log.side_effect = RuntimeError("boom")
    with (
        patch("flint.core.logs._load_k8s_config"),
        patch("kubernetes.client.CoreV1Api", return_value=api),
    ):
        with pytest.raises(K8sError, match="Failed to read logs"):
            list(iter_pod_logs("m", "flint"))
