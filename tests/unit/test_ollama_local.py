"""Tests for flint.core.runtimes.ollama_local."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from flint.core.errors import OllamaError, OllamaNotFoundError, OllamaUnhealthyError
from flint.core.runtimes.ollama_local import (
    _normalise_model,
    is_available,
    is_model_local,
    list_local_models,
    pull,
    serve,
    wait_healthy,
)

# -- _normalise_model (pure) --------------------------------------------------


def test_normalise_adds_latest_tag() -> None:
    assert _normalise_model("tinyllama") == "tinyllama:latest"


def test_normalise_preserves_existing_tag() -> None:
    assert _normalise_model("llama3:8b") == "llama3:8b"


# -- is_available -------------------------------------------------------------


def test_is_available_true_when_found() -> None:
    with patch("shutil.which", return_value="/usr/local/bin/ollama"):
        assert is_available() is True


def test_is_available_false_when_not_found() -> None:
    with patch("shutil.which", return_value=None):
        assert is_available() is False


# -- list_local_models --------------------------------------------------------


_LIST_OUTPUT = (
    "NAME               ID              SIZE      MODIFIED\n"
    "tinyllama:latest   2644915ede35    637 MB    2 weeks ago\n"
    "llama3:8b          abc123def456    4.7 GB    3 days ago\n"
)


def test_list_local_models_parses_output() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=_LIST_OUTPUT, stderr=""
        )
        models = list_local_models()
    assert "tinyllama:latest" in models
    assert "llama3:8b" in models


def test_list_local_models_empty_on_failure() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="connection refused"
        )
        models = list_local_models()
    assert models == []


def test_list_local_models_skips_header() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=_LIST_OUTPUT, stderr=""
        )
        models = list_local_models()
    # Header line "NAME ..." should not be included
    assert not any("NAME" in m for m in models)


# -- is_model_local -----------------------------------------------------------


def test_is_model_local_found() -> None:
    with patch("flint.core.runtimes.ollama_local.list_local_models",
               return_value=["tinyllama:latest"]):
        assert is_model_local("tinyllama") is True


def test_is_model_local_not_found() -> None:
    with patch("flint.core.runtimes.ollama_local.list_local_models",
               return_value=["llama3:8b"]):
        assert is_model_local("tinyllama") is False


def test_is_model_local_exact_tag_match() -> None:
    with patch("flint.core.runtimes.ollama_local.list_local_models",
               return_value=["tinyllama:1.1"]):
        assert is_model_local("tinyllama:1.1") is True


# -- wait_healthy -------------------------------------------------------------


def test_wait_healthy_succeeds_on_200() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.get", return_value=mock_resp):
        wait_healthy(port=11434, timeout_s=5)  # should not raise


def test_wait_healthy_retries_until_success() -> None:
    call_count = 0
    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_fail = MagicMock()
    mock_resp_fail.status_code = 503

    def side_effect(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        return mock_resp_ok if call_count >= 3 else mock_resp_fail

    with patch("httpx.get", side_effect=side_effect), patch("time.sleep"):
        wait_healthy(port=11434, timeout_s=5)
    assert call_count >= 3


def test_wait_healthy_raises_on_timeout() -> None:
    import httpx as _httpx

    with (
        patch("httpx.get", side_effect=_httpx.ConnectError("refused")),
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0.0, 0.5, 31.0]),
    ):
        with pytest.raises(OllamaUnhealthyError, match="healthy"):
            wait_healthy(port=11434, timeout_s=30)


def test_wait_healthy_request_error_does_not_raise_immediately() -> None:
    import httpx as _httpx

    responses = [
        _httpx.ConnectError("refused"),
        MagicMock(status_code=200),
    ]
    call_iter = iter(responses)

    def side_effect(*args: object, **kwargs: object) -> object:
        r = next(call_iter)
        if isinstance(r, Exception):
            raise r
        return r

    with patch("httpx.get", side_effect=side_effect), patch("time.sleep"):
        wait_healthy(port=11434, timeout_s=5)  # should succeed on second attempt


# -- serve --------------------------------------------------------------------


def test_serve_returns_popen_when_available() -> None:
    mock_proc = MagicMock()
    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
    ):
        proc = serve("tinyllama", port=11434)
    assert proc is mock_proc
    mock_popen.assert_called_once()
    args = mock_popen.call_args[0][0]
    assert args == ["ollama", "serve"]


def test_serve_sets_ollama_host_env() -> None:
    mock_proc = MagicMock()
    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
    ):
        serve("tinyllama", port=12345)
    env = mock_popen.call_args[1]["env"]
    assert env["OLLAMA_HOST"] == "0.0.0.0:12345"


def test_serve_raises_when_ollama_not_available() -> None:
    with patch("flint.core.runtimes.ollama_local.is_available", return_value=False):
        with pytest.raises(OllamaNotFoundError, match="not installed"):
            serve("tinyllama")


# -- pull ---------------------------------------------------------------------


def test_pull_yields_lines() -> None:
    mock_proc = MagicMock()
    mock_proc.stdout.__iter__ = MagicMock(
        return_value=iter(["pulling...\n", "done\n"])
    )
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0

    with patch("subprocess.Popen", return_value=mock_proc):
        lines = list(pull("tinyllama"))
    assert "pulling..." in lines
    assert "done" in lines


def test_pull_raises_on_nonzero_exit() -> None:
    mock_proc = MagicMock()
    mock_proc.stdout.__iter__ = MagicMock(return_value=iter([]))
    mock_proc.wait.return_value = None
    mock_proc.returncode = 1

    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(OllamaError, match="Failed to pull"):
            list(pull("nonexistent-model"))
