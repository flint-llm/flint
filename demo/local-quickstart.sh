#!/usr/bin/env bash
#
# Flint local quickstart — a ~60-second demo of serving a model locally behind
# an OpenAI-compatible endpoint. Runnable on any laptop.
#
# Requires: `pip install flint-llm` and Ollama installed (https://ollama.com).
# Record a cast with:
#     asciinema rec -c "bash demo/local-quickstart.sh" flint-local.cast
#
set -euo pipefail

step() { printf '\n\033[1;36m$ %s\033[0m\n' "$*"; sleep 1; }

step "flint version"
flint version
sleep 1

step "flint serve tinyllama    # OpenAI-compatible endpoint on :11434"
flint serve tinyllama >/tmp/flint-demo-serve.log 2>&1 &
SERVE_PID=$!
trap 'kill -TERM "$SERVE_PID" 2>/dev/null || true' EXIT
printf 'waiting for the model'
until curl -sf http://localhost:11434/api/tags 2>/dev/null | grep -q tinyllama; do
  printf '.'; sleep 1
done
printf '\nEndpoint ready: http://localhost:11434/v1\n'
sleep 1

step 'curl -N localhost:11434/v1/chat/completions   # streamed'
curl -sN http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"tinyllama","stream":true,
       "messages":[{"role":"user","content":"Say hello in one short sentence."}]}' \
  | grep -o '"content":"[^"]*"' | sed 's/"content":"//;s/"$//' | tr -d '\n'
printf '\n'
sleep 1

step "Ctrl+C   # clean shutdown, no leftover processes"
kill -TERM "$SERVE_PID" 2>/dev/null || true
wait "$SERVE_PID" 2>/dev/null || true
trap - EXIT
echo "Stopped."
