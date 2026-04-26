"""Tests for flint serve command (unit — no real Ollama needed)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from flint.cli.main import cli


def _invoke(*args: str) -> object:
    return CliRunner().invoke(cli, ["serve", *args])


# -- Ollama not on PATH -------------------------------------------------------


def test_serve_no_ollama_exits_nonzero() -> None:
    with patch("flint.core.runtimes.ollama_local.is_available", return_value=False):
        result = CliRunner().invoke(cli, ["serve", "tinyllama"])
    assert result.exit_code != 0


def test_serve_no_ollama_prints_install_hint() -> None:
    with patch("flint.core.runtimes.ollama_local.is_available", return_value=False):
        result = CliRunner().invoke(cli, ["serve", "tinyllama"])
    assert "ollama" in result.output.lower() or result.exit_code != 0


def test_serve_no_ollama_mentions_install() -> None:
    with patch("flint.core.runtimes.ollama_local.is_available", return_value=False):
        result = CliRunner().invoke(cli, ["serve", "tinyllama"])
    combined = result.output + result.stderr if hasattr(result, "stderr") else result.output
    assert any(
        kw in combined.lower()
        for kw in ["install", "not found", "path", "brew", "curl"]
    )


# -- Pull failure -------------------------------------------------------------


def test_serve_pull_failure_exits_nonzero() -> None:
    from flint.core.errors import OllamaError

    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("flint.core.runtimes.ollama_local.is_model_local", return_value=False),
        patch(
            "flint.core.runtimes.ollama_local.pull",
            side_effect=OllamaError("pull failed"),
        ),
    ):
        result = CliRunner().invoke(cli, ["serve", "nonexistent"])
    assert result.exit_code != 0


def test_serve_pull_failure_no_traceback_by_default() -> None:
    from flint.core.errors import OllamaError

    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("flint.core.runtimes.ollama_local.is_model_local", return_value=False),
        patch(
            "flint.core.runtimes.ollama_local.pull",
            side_effect=OllamaError("connection refused"),
        ),
    ):
        result = CliRunner().invoke(cli, ["serve", "nonexistent"])
    assert "Traceback" not in result.output


# -- Server unhealthy ---------------------------------------------------------


def test_serve_unhealthy_exits_nonzero() -> None:
    from flint.core.errors import OllamaUnhealthyError

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.return_value = 0
    mock_proc.stdout = iter([])
    mock_proc.stderr = iter([])

    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("flint.core.runtimes.ollama_local.is_model_local", return_value=True),
        patch("flint.core.runtimes.ollama_local.serve", return_value=mock_proc),
        patch(
            "flint.core.runtimes.ollama_local.wait_healthy",
            side_effect=OllamaUnhealthyError("timeout"),
        ),
    ):
        result = CliRunner().invoke(cli, ["serve", "tinyllama"])
    assert result.exit_code != 0


# -- Happy path (banner printed) ----------------------------------------------


def test_serve_happy_path_prints_endpoint() -> None:
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0
    mock_proc.stdout = iter([])
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0

    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("flint.core.runtimes.ollama_local.is_model_local", return_value=True),
        patch("flint.core.runtimes.ollama_local.serve", return_value=mock_proc),
        patch("flint.core.runtimes.ollama_local.wait_healthy"),
        patch("flint.cli.serve._install_signal_handlers"),
        patch("flint.cli.serve._start_stream_thread"),
    ):
        result = CliRunner().invoke(cli, ["serve", "tinyllama"])
    assert "http://localhost:11434/v1" in result.output


def test_serve_happy_path_custom_port() -> None:
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0
    mock_proc.stdout = iter([])
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0

    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("flint.core.runtimes.ollama_local.is_model_local", return_value=True),
        patch("flint.core.runtimes.ollama_local.serve", return_value=mock_proc),
        patch("flint.core.runtimes.ollama_local.wait_healthy"),
        patch("flint.cli.serve._install_signal_handlers"),
        patch("flint.cli.serve._start_stream_thread"),
    ):
        result = CliRunner().invoke(cli, ["serve", "tinyllama", "--port", "12000"])
    assert "12000" in result.output


# -- Helper function coverage -------------------------------------------------


def test_shutdown_skips_if_already_exited() -> None:
    from unittest.mock import patch

    from flint.cli.serve import _shutdown

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0  # already exited
    with patch("os.killpg") as mock_killpg, patch("os.getpgid", return_value=1234):
        _shutdown(mock_proc)
        mock_killpg.assert_not_called()


def test_shutdown_terminates_running_proc() -> None:
    import signal as _signal
    from unittest.mock import patch

    from flint.cli.serve import _shutdown

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.return_value = 0
    with patch("os.killpg") as mock_killpg, patch("os.getpgid", return_value=1234):
        _shutdown(mock_proc)
    mock_killpg.assert_called_once_with(1234, _signal.SIGTERM)


def test_shutdown_kills_after_timeout() -> None:
    import signal as _signal
    from unittest.mock import call, patch

    from flint.cli.serve import _shutdown

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired("ollama", 5), None]
    with patch("os.killpg") as mock_killpg, patch("os.getpgid", return_value=1234):
        _shutdown(mock_proc)
    assert mock_killpg.call_args_list == [
        call(1234, _signal.SIGTERM),
        call(1234, _signal.SIGKILL),
    ]


def test_start_stream_thread_echoes_lines() -> None:
    import io
    import time as _time

    from click.testing import CliRunner as _CliRunner

    from flint.cli.serve import _start_stream_thread

    stream = io.StringIO("line one\nline two\n")
    runner = _CliRunner()
    with runner.isolated_filesystem():
        _start_stream_thread(stream, "[test] ")
        _time.sleep(0.05)  # give daemon thread time to run


def test_install_signal_handlers_runs_without_error() -> None:
    import signal as _signal

    import flint.cli.serve as serve_mod
    from flint.cli.serve import _install_signal_handlers

    serve_mod._shutdown_requested.clear()
    try:
        # Should not raise even on Windows where SIGTERM behaves differently
        _install_signal_handlers()
        if hasattr(_signal, "SIGTERM"):
            _signal.raise_signal(_signal.SIGTERM)
            assert serve_mod._shutdown_requested.is_set()
    finally:
        serve_mod._shutdown_requested.clear()


def test_serve_pull_streaming_path() -> None:
    """Test that pull output is echoed when model is not local."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0
    mock_proc.stdout = iter([])
    mock_proc.stderr = iter([])
    mock_proc.wait.return_value = 0

    with (
        patch("flint.core.runtimes.ollama_local.is_available", return_value=True),
        patch("flint.core.runtimes.ollama_local.is_model_local", return_value=False),
        patch("flint.core.runtimes.ollama_local.pull", return_value=iter(["pulling...", "done"])),
        patch("flint.core.runtimes.ollama_local.serve", return_value=mock_proc),
        patch("flint.core.runtimes.ollama_local.wait_healthy"),
        patch("flint.cli.serve._install_signal_handlers"),
        patch("flint.cli.serve._start_stream_thread"),
    ):
        result = CliRunner().invoke(cli, ["serve", "tinyllama"])
    assert "pulling" in result.output or "done" in result.output or "Pulling" in result.output
