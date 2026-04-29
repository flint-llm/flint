"""flint serve command — local mode via Ollama.

Lifecycle:
  1. Verify ollama is on PATH (or print install hint and exit)
  2. Start `ollama serve` as a subprocess
  3. Wait up to 30s for the server to be healthy
  4. Check if the model is already pulled locally; pull if not
     (this step talks to the daemon we just started)
  5. Print the endpoint banner
  6. Stream Ollama's stdout/stderr to the terminal
  7. On SIGTERM or Ctrl+C: SIGTERM the subprocess, SIGKILL after 5s timeout

Windows is out of scope for `flint serve` (macOS and Linux only).
`flint version` and `flint init` work on all platforms.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from typing import IO

import click

from flint.cli._errors import handle_flint_error
from flint.core.errors import OllamaError, OllamaNotFoundError, OllamaUnhealthyError
from flint.core.runtimes import ollama_local as ollama

_INSTALL_HINT = (
    "  macOS:  brew install ollama\n"
    "  Linux:  curl -fsSL https://ollama.com/install.sh | sh"
)

_BANNER = """\
\nEndpoint:  http://localhost:{port}/v1
Example:   curl -N http://localhost:{port}/v1/chat/completions \\
               -H "Content-Type: application/json" \\
               -d '{{"model": "{model}", "stream": true, "messages": [{{"role": "user", "content": "hi"}}]}}'

Press Ctrl+C to stop.
"""

_shutdown_requested: threading.Event = threading.Event()


@click.command("serve")
@click.argument("model")
@click.option(
    "--port",
    default=ollama.DEFAULT_PORT,
    show_default=True,
    help="Port for the Ollama server.",
)
@click.pass_context
def serve(ctx: click.Context, model: str, port: int) -> None:
    """Serve MODEL locally via Ollama (OpenAI-compatible endpoint)."""
    # 1. Check Ollama is installed
    if not ollama.is_available():
        click.echo(
            "Error: ollama not found on PATH. Install it first:\n" + _INSTALL_HINT,
            err=True,
        )
        sys.exit(1)

    # 2. Start ollama serve
    try:
        proc = ollama.serve(model, port)
    except OllamaNotFoundError as exc:
        handle_flint_error(exc, ctx)
        return

    # 3. Wait for healthy
    try:
        ollama.wait_healthy(port, timeout_s=30)
    except OllamaUnhealthyError as exc:
        _shutdown(proc)
        handle_flint_error(exc, ctx)
        return

    # 4. Pull model if not already local (the daemon we just started
    #    handles the pull, so this works even with no pre-existing daemon).
    if not ollama.is_model_local(model, port=port):
        click.echo(f"Pulling {model}...")
        try:
            for line in ollama.pull(model, port=port):
                click.echo(line)
        except OllamaError as exc:
            _shutdown(proc)
            handle_flint_error(exc, ctx)
            return  # unreachable but satisfies type checker

    # 5. Install signal handlers for clean shutdown
    _install_signal_handlers()

    # 6. Print banner
    click.echo(_BANNER.format(port=port, model=model))

    # 7. Stream subprocess output in background threads
    assert proc.stdout is not None
    assert proc.stderr is not None
    _start_stream_thread(proc.stdout, "[ollama] ")
    _start_stream_thread(proc.stderr, "[ollama] ")

    exit_code = _main_loop(proc)
    sys.exit(exit_code)


# -- Helpers ------------------------------------------------------------------


def _main_loop(proc: subprocess.Popen[str]) -> int:
    """Poll until the subprocess exits or shutdown is requested."""
    while True:
        if _shutdown_requested.is_set():
            click.echo("\nStopping...", err=True)
            _shutdown(proc)
            click.echo("Stopped.")
            return 0
        try:
            exit_code = proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            continue
        except KeyboardInterrupt:
            _shutdown_requested.set()
            continue
        return exit_code if exit_code is not None else 1


def _start_stream_thread(stream: IO[str], prefix: str) -> None:
    """Spawn a daemon thread that echoes lines from *stream* with *prefix*."""

    def _run() -> None:
        for line in stream:
            click.echo(f"{prefix}{line}", nl=False)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _shutdown(proc: subprocess.Popen[str]) -> None:
    """Gracefully stop *proc* and its process group: SIGTERM, then SIGKILL after 5s."""
    if proc.poll() is not None:
        return  # already exited
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def _install_signal_handlers() -> None:
    """Install SIGTERM handler to request clean shutdown.

    SIGINT (Ctrl+C) is handled inside _main_loop via KeyboardInterrupt.
    SIGTERM (e.g. from systemd or the E2E test harness) is handled here.
    Signal handlers are only available on Unix.
    """
    if not hasattr(signal, "SIGTERM"):
        return

    def _handler(signum: int, frame: object) -> None:
        _shutdown_requested.set()

    signal.signal(signal.SIGTERM, _handler)
