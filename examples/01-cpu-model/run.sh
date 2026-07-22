#!/usr/bin/env bash
#
# Flint example 01 — deploy a small model on CPU (Ollama runtime).
#
#   ./run.sh            deploy tinyllama, call it, show logs
#   ./run.sh cleanup    delete everything this example created
#
# Env: NAMESPACE (default flint-example-01), LOCAL_PORT (default 18081)
set -euo pipefail

NAMESPACE="${NAMESPACE:-flint-example-01}"
LOCAL_PORT="${LOCAL_PORT:-18081}"
MODEL="tinyllama"
SVC="${MODEL}-latest"          # flint names resources <model>-<version>

say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
run()  { printf '\033[2m$ %s\033[0m\n' "$*"; "$@"; }

if [[ "${1:-}" == "cleanup" ]]; then
  say "Deleting $MODEL and the namespace"
  flint delete "$MODEL" -n "$NAMESPACE" --yes || true
  kubectl delete namespace "$NAMESPACE" --ignore-not-found
  echo "Done."
  exit 0
fi

# --- preflight ---------------------------------------------------------------
for bin in flint kubectl; do
  command -v "$bin" >/dev/null || { echo "error: $bin not found on PATH" >&2; exit 1; }
done
kubectl cluster-info >/dev/null 2>&1 || {
  echo "error: no reachable cluster. Check: kubectl config current-context" >&2
  exit 1
}
echo "Cluster:   $(kubectl config current-context)"
echo "Namespace: $NAMESPACE"

# --- 1. deploy ---------------------------------------------------------------
# Ollama serves on CPU, so this works on any cluster — including kind. The
# model is pulled by an init container before the server starts, so "ready"
# genuinely means "able to answer".
say "Deploying $MODEL on the Ollama runtime (first run pulls ~640MB)"
run flint deploy "$MODEL" \
  --runtime ollama \
  --namespace "$NAMESPACE" \
  --wait --wait-timeout 900

# --- 2. inspect --------------------------------------------------------------
say "Status"
run flint status "$MODEL" -n "$NAMESPACE"

say "Everything Flint manages in this namespace"
run flint list -n "$NAMESPACE"

# --- 3. call it --------------------------------------------------------------
# The Service is ClusterIP, so reach it with a port-forward.
say "Port-forwarding svc/$SVC to localhost:$LOCAL_PORT"
kubectl port-forward "svc/$SVC" "$LOCAL_PORT:80" -n "$NAMESPACE" >/dev/null 2>&1 &
PF_PID=$!
trap 'kill "$PF_PID" 2>/dev/null || true' EXIT

for _ in $(seq 30); do
  curl -sf "http://localhost:$LOCAL_PORT/api/tags" >/dev/null 2>&1 && break
  sleep 1
done
curl -sf "http://localhost:$LOCAL_PORT/api/tags" >/dev/null 2>&1 || {
  echo "error: port-forward never became reachable" >&2; exit 1; }

say "Chat completion (OpenAI-compatible)"
curl -s "http://localhost:$LOCAL_PORT/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",
       \"messages\":[{\"role\":\"user\",\"content\":\"Name one planet. One word.\"}],
       \"max_tokens\":16}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"].strip())'

# --- 4. logs -----------------------------------------------------------------
say "Runtime logs (last 10 lines)"
run flint logs "$MODEL" -n "$NAMESPACE" --tail 10

cat <<EOF

$(printf '\033[1;32m✓ Example 01 complete.\033[0m')

The model is still running. Try:
  flint status $MODEL -n $NAMESPACE
  flint logs $MODEL -n $NAMESPACE --follow
  kubectl -n $NAMESPACE get all -l flint.dev/managed=true

Tear it down with:
  ./run.sh cleanup
EOF
