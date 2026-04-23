"""flint serve command — local mode via Ollama.

Lifecycle:
  1. Verify ollama is on PATH (or print install hint and exit)
  2. Check if the model is already pulled locally; pull if not
  3. Start `ollama serve` as a subprocess
  4. Wait up to 30s for the server to be healthy
  5. Print the endpoint banner
  6. Stream Ollama's stdout/stderr to the terminal
  7. On SIGTERM or Ctrl+C: SIGTERM the subprocess, SIGKILL after 5s timeout

Windows is out of scope for `flint serve` (macOS and Linux only).
`flint version` and `flint init` work on all platforms.
"""

from __future__ import annotations

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

    # 2. Pull model if not already local (best-effort — may fail if no
    #    existing daemon is running; user can pre-pull with `ollama pull`)
    if not ollama.is_model_local(model):
        click.echo(f"Pulling {model}...")
        try:
            for line in ollama.pull(model):
                click.echo(line)
        except OllamaError as exc:
            handle_flint_error(exc, ctx)
            return  # unreachable but satisfies type checker

    # 3. Start ollama serve
    try:
        proc = ollama.serve(model, port)
    except OllamaNotFoundError as exc:
        handle_flint_error(exc, ctx)
        return

    # 4. Wait for healthy
    try:
        ollama.wait_healthy(port, timeout_s=30)
    except OllamaUnhealthyError as exc:
        _shutdown(proc)
        handle_flint_error(exc, ctx)
        return

    # 5. Install signal handlers for clean shutdown
    _install_signal_handlers(proc)

    # 6. Print banner
    click.echo(_BANNER.format(port=port, model=model))

    # 7. Stream subprocess output in background threads
    assert proc.stdout is not None
    assert proc.stderr is not None
    _start_stream_thread(proc.stdout, "[ollama] ")
    _start_stream_thread(proc.stderr, "[ollama] ")

    # Block until the subprocess exits or Ctrl+C is received
    try:
        proc.wait()
    except KeyboardInterrupt:
        click.echo("\nStopping...", err=True)
        _shutdown(proc)
        click.echo("Stopped.")
        sys.exit(0)

    # Subprocess exited on its own (unexpected)
    click.echo(
        f"ollama serve exited with code {proc.returncode}.", err=True
    )
    sys.exit(proc.returncode or 1)


# -- Helpers ------------------------------------------------------------------


def _start_stream_thread(stream: IO[str], prefix: str) -> None:
    """Spawn a daemon thread that echoes lines from *stream* with *prefix*."""

    def _run() -> None:
        for line in stream:
            click.echo(f"{prefix}{line}", nl=False)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _shutdown(proc: subprocess.Popen[str]) -> None:
    """Gracefully stop *proc*: SIGTERM, then SIGKILL after 5s."""
    if proc.poll() is not None:
        return  # already exited
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _install_signal_handlers(proc: subprocess.Popen[str]) -> None:
    """Install SIGTERM handler to clean up the subprocess on termination.

    SIGINT (Ctrl+C) is handled by the KeyboardInterrupt catch in serve().
    SIGTERM (e.g. from systemd or the E2E test harness) is handled here.
    Signal handlers are only available on Unix.
    """
    if not hasattr(signal, "SIGTERM"):
        return

    def _handler(signum: int, frame: object) -> None:
        _shutdown(proc)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handler)
