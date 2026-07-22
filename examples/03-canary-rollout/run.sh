#!/usr/bin/env bash
#
# Flint example 03 — canary rollout between two versions of a model.
#
#   ./run.sh                     run the full rollout: 100/0 -> 90/10 -> 50/50 -> 0/100
#   INSTALL_GATEWAY=1 ./run.sh   also install Envoy Gateway if it is missing
#   ./run.sh cleanup             delete everything this example created
#
# Env: NAMESPACE (default flint-example-03), LOCAL_PORT (default 18083),
#      SAMPLES (default 200), EG_VERSION (default v1.8.2)
set -euo pipefail

NAMESPACE="${NAMESPACE:-flint-example-03}"
LOCAL_PORT="${LOCAL_PORT:-18083}"
SAMPLES="${SAMPLES:-200}"
EG_VERSION="${EG_VERSION:-v1.8.2}"
MODEL="tinyllama"
HOST="${MODEL}.local"            # flint route's default hostname: <model>.local
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
run()  { printf '\033[2m$ %s\033[0m\n' "$*"; "$@"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

if [[ "${1:-}" == "cleanup" ]]; then
  say "Deleting the model (this also removes its HTTPRoute), Gateway and namespace"
  flint delete "$MODEL" -n "$NAMESPACE" --yes || true
  kubectl delete gateway flint-gateway -n "$NAMESPACE" --ignore-not-found
  kubectl delete namespace "$NAMESPACE" --ignore-not-found
  kubectl delete gatewayclass flint-eg --ignore-not-found
  echo
  echo "Envoy Gateway itself was left installed. Remove it with:"
  echo "  kubectl delete -f https://github.com/envoyproxy/gateway/releases/download/${EG_VERSION}/install.yaml"
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

# --- 1. Gateway API implementation -------------------------------------------
# Flint requires one but never installs it — a gateway controller is a
# cluster-wide component and yours to own.
if ! kubectl get crd httproutes.gateway.networking.k8s.io >/dev/null 2>&1; then
  if [[ "${INSTALL_GATEWAY:-}" == "1" ]]; then
    say "Installing Envoy Gateway $EG_VERSION (CRDs + controller)"
    kubectl apply --server-side -f \
      "https://github.com/envoyproxy/gateway/releases/download/${EG_VERSION}/install.yaml"
    kubectl wait --timeout=300s -n envoy-gateway-system \
      deployment/envoy-gateway --for=condition=Available
  else
    cat >&2 <<EOF

error: no Gateway API implementation found in this cluster.

This example needs one. To install Envoy Gateway $EG_VERSION into *your*
cluster (a cluster-wide change), re-run with:

    INSTALL_GATEWAY=1 ./run.sh

Or install it yourself:
    kubectl apply --server-side -f https://github.com/envoyproxy/gateway/releases/download/${EG_VERSION}/install.yaml
EOF
    exit 1
  fi
fi

# --- 2. namespace + Gateway ---------------------------------------------------
say "Creating the namespace and the Gateway Flint will attach routes to"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
sed "s/NAMESPACE_PLACEHOLDER/$NAMESPACE/" "$HERE/gateway.yaml" | kubectl apply -f -

# --- 3. two versions ----------------------------------------------------------
# Same model name, two version tags => two Deployments and two Services named
# tinyllama-v1 and tinyllama-v2. Those Services are what the split weighs.
for v in v1 v2; do
  say "Deploying $MODEL:$v (first one pulls ~640MB)"
  run flint deploy "$MODEL" \
    --runtime ollama --version "$v" \
    --namespace "$NAMESPACE" \
    --wait --wait-timeout 900
done

run flint list -n "$NAMESPACE"

# --- 4. port-forward the gateway data plane -----------------------------------
# On kind there is no LoadBalancer, so the Gateway never gets an external
# address. Port-forward the Envoy proxy Service directly instead.
say "Waiting for the Envoy proxy that fronts this Gateway"
OWNER="gateway.envoyproxy.io/owning-gateway-name=flint-gateway"
for _ in $(seq 60); do
  PROXY_SVC=$(kubectl get svc -n envoy-gateway-system -l "$OWNER" \
              -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  [[ -n "${PROXY_SVC:-}" ]] && break
  sleep 3
done
[[ -n "${PROXY_SVC:-}" ]] || { echo "error: no Envoy proxy Service for the Gateway" >&2; exit 1; }

# The proxy Deployment can lag its Service; `kubectl wait` errors out with "no
# matching resources found" rather than waiting, so poll for it to exist first.
for _ in $(seq 60); do
  PROXY_DEPLOY=$(kubectl get deploy -n envoy-gateway-system -l "$OWNER" \
                 -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  [[ -n "${PROXY_DEPLOY:-}" ]] && break
  sleep 3
done
[[ -n "${PROXY_DEPLOY:-}" ]] || { echo "error: no Envoy proxy Deployment for the Gateway" >&2; exit 1; }
kubectl wait --for=condition=Available "deploy/$PROXY_DEPLOY" \
  -n envoy-gateway-system --timeout=300s

kubectl port-forward "svc/$PROXY_SVC" "$LOCAL_PORT:80" -n envoy-gateway-system >/dev/null 2>&1 &
PF_PID=$!
trap 'kill "$PF_PID" 2>/dev/null || true' EXIT
sleep 3

# --- helpers ------------------------------------------------------------------
# Count requests each version actually served, as a delta across the sampling
# window. (Readiness probes hit the same endpoint, so a few extra hits per pod
# are expected — that is the noise floor, not the signal.)
hits() {
  kubectl logs -n "$NAMESPACE" -l "flint.dev/version=$1" --tail=-1 2>/dev/null \
    | grep -c "/api/tags" || true
}

sample() {          # sample <expected-description>
  local before_v1 before_v2 after_v1 after_v2 d1 d2 total
  before_v1=$(hits v1); before_v2=$(hits v2)
  for _ in $(seq "$SAMPLES"); do
    curl -s -o /dev/null -H "Host: $HOST" "http://localhost:$LOCAL_PORT/api/tags" || true
  done
  sleep 2                       # let the pods flush their logs
  after_v1=$(hits v1); after_v2=$(hits v2)
  d1=$(( after_v1 - before_v1 )); d2=$(( after_v2 - before_v2 ))
  total=$(( d1 + d2 ))
  if (( total == 0 )); then
    echo "  (no requests observed — is the route live?)"
    return
  fi
  # Round rather than truncate, so the two percentages read as a split.
  printf '  observed: v1 %3d%%  v2 %3d%%   (%d of %d requests)   expected: %s\n' \
    $(( (d1 * 200 + total) / (total * 2) )) $(( (d2 * 200 + total) / (total * 2) )) \
    "$total" "$SAMPLES" "$1"
}

wait_for_route() {
  for _ in $(seq 60); do
    curl -sf -o /dev/null -H "Host: $HOST" "http://localhost:$LOCAL_PORT/api/tags" && return 0
    sleep 1
  done
  echo "error: the route never became live through the Gateway" >&2
  exit 1
}

# --- 5. the rollout -----------------------------------------------------------
say "Baseline — all traffic to v1"
run flint route "$MODEL" --to v1 -n "$NAMESPACE"
wait_for_route
sample "v1 100% / v2 0%"

say "Canary — 10% to v2"
run flint route "$MODEL" --canary 10 v2 -n "$NAMESPACE"
sleep 5
sample "v1 90% / v2 10%"

say "Widen — 50/50"
run flint route "$MODEL" --canary 50 v2 -n "$NAMESPACE"
sleep 5
sample "v1 50% / v2 50%"

say "Cut over — all traffic to v2"
run flint route "$MODEL" --to v2 -n "$NAMESPACE"
sleep 5
sample "v1 0% / v2 100%"

# --- 6. where things stand ----------------------------------------------------
say "Current split"
run flint route "$MODEL" --show -n "$NAMESPACE"

say "Status (readiness and the split together)"
run flint status "$MODEL" -n "$NAMESPACE"

say "A real completion through the Gateway"
curl -s -H "Host: $HOST" -H "Content-Type: application/json" \
  "http://localhost:$LOCAL_PORT/v1/chat/completions" \
  -d "{\"model\":\"$MODEL\",
       \"messages\":[{\"role\":\"user\",\"content\":\"Name one color. One word.\"}],
       \"max_tokens\":16}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"].strip())'

bold "
✓ Example 03 complete."
cat <<EOF

v1 is still deployed but receives no traffic. Roll back instantly with:
  flint route $MODEL --to v1 -n $NAMESPACE

Or retire the old version once you trust v2:
  flint delete $MODEL --version v1 -n $NAMESPACE --yes

Tear everything down:
  ./run.sh cleanup
EOF
