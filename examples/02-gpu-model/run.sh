#!/usr/bin/env bash
#
# Flint example 02 — deploy a 7B model on GPU with vLLM.
#
#   ./run.sh            deploy, wait for readiness, run a completion
#   ./run.sh cleanup    delete everything this example created
#
# Env:
#   NAMESPACE     default flint-example-02
#   MODEL         default mistral            (a DNS-1123 label; the served name)
#   HF_REPO       default mistralai/Mistral-7B-Instruct-v0.3
#   HF_TOKEN      optional; creates a Secret for gated/private repos
#   GPUS          default 1
#   LOCAL_PORT    default 18082
set -euo pipefail

NAMESPACE="${NAMESPACE:-flint-example-02}"
MODEL="${MODEL:-mistral}"
HF_REPO="${HF_REPO:-mistralai/Mistral-7B-Instruct-v0.3}"
GPUS="${GPUS:-1}"
LOCAL_PORT="${LOCAL_PORT:-18082}"
SECRET="hf-token"
SVC="${MODEL}-latest"

say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
run() { printf '\033[2m$ %s\033[0m\n' "$*"; "$@"; }

if [[ "${1:-}" == "cleanup" ]]; then
  say "Deleting $MODEL and the namespace"
  # Without --keep-weights this also removes the weights PVC, so the next
  # deploy re-downloads ~15GB. Pass --keep-weights if you plan to come back.
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

# Fail early with a clear message rather than leaving a Pod Pending forever.
say "Checking for GPU capacity"
gpu_total=$(kubectl get nodes -o jsonpath='{range .items[*]}{.status.capacity.nvidia\.com/gpu}{"\n"}{end}' \
            | awk '{s+=$1} END {print s+0}')
echo "Allocatable nvidia.com/gpu across nodes: ${gpu_total}"
if [[ "$gpu_total" -lt "$GPUS" ]]; then
  cat >&2 <<EOF

error: this example needs ${GPUS} GPU(s) but the cluster advertises ${gpu_total}.

  - GPU nodes must run the NVIDIA device plugin for 'nvidia.com/gpu' to appear.
  - No GPUs available? Run example 01 instead (CPU, Ollama):
        cd ../01-cpu-model && ./run.sh
EOF
  exit 1
fi

echo "Cluster:   $(kubectl config current-context)"
echo "Namespace: $NAMESPACE"
echo "Model:     $MODEL  <-  $HF_REPO"

# --- 1. optional HF token ----------------------------------------------------
# Gated repos (Llama, some Mistral builds) need a HuggingFace token. Flint reads
# it from a Secret with the key 'token'.
HF_ARGS=()
if [[ -n "${HF_TOKEN:-}" ]]; then
  say "Creating Secret/$SECRET for gated repo access"
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
  kubectl create secret generic "$SECRET" \
    --from-literal=token="$HF_TOKEN" \
    -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
  HF_ARGS=(--hf-token-secret "$SECRET")
else
  echo "(HF_TOKEN not set — assuming '$HF_REPO' is public)"
fi

# --- 2. deploy ---------------------------------------------------------------
# vLLM downloads weights into a PVC mounted at /weights (HF_HOME), so a
# restarted pod does not re-download them. 50Gi is the default; a 7B model in
# bf16 is ~15GB.
say "Deploying $MODEL on vLLM with $GPUS GPU(s)"
run flint deploy "$MODEL" \
  --runtime vllm \
  --hf-repo "$HF_REPO" \
  --gpu "$GPUS" \
  --namespace "$NAMESPACE" \
  --weights-volume-size 50Gi \
  --memory-request 16Gi --memory-limit 32Gi \
  ${HF_ARGS[@]+"${HF_ARGS[@]}"} \
  --wait --wait-timeout 1800

# --- 3. inspect --------------------------------------------------------------
say "Status"
run flint status "$MODEL" -n "$NAMESPACE"

# --- 4. call it --------------------------------------------------------------
say "Port-forwarding svc/$SVC to localhost:$LOCAL_PORT"
kubectl port-forward "svc/$SVC" "$LOCAL_PORT:80" -n "$NAMESPACE" >/dev/null 2>&1 &
PF_PID=$!
trap 'kill "$PF_PID" 2>/dev/null || true' EXIT

for _ in $(seq 60); do
  curl -sf "http://localhost:$LOCAL_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done

say "Models the server reports"
curl -s "http://localhost:$LOCAL_PORT/v1/models" | python3 -m json.tool || true

say "Chat completion"
curl -s "http://localhost:$LOCAL_PORT/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",
       \"messages\":[{\"role\":\"user\",\"content\":\"Explain KV caching in one sentence.\"}],
       \"max_tokens\":80}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"].strip())'

cat <<EOF

$(printf '\033[1;32m✓ Example 02 complete.\033[0m')

Still running. Try:
  flint logs $MODEL -n $NAMESPACE --follow
  kubectl -n $NAMESPACE get pvc               # the weights volume

Tear it down (this deletes the weights PVC too):
  ./run.sh cleanup

Keep the weights for next time instead:
  flint delete $MODEL -n $NAMESPACE --keep-weights --yes
EOF
