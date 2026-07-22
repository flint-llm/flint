# 03 — Canary rollout between two versions

Run two versions of a model side by side and move traffic between them:
**100/0 → 90/10 → 50/50 → 0/100**, measuring the split that actually happens at
each step. No GPU required.

This is the example worth reading. Deploying a model is table stakes; changing
which model answers production traffic, gradually and reversibly, is the point.

- **Time:** ~15 minutes
- **Needs:** any cluster (kind is fine), a Gateway API implementation,
  `kubectl`, `flint`, `curl`, `python3`

## Run it

```bash
pip install flint-llm
./run.sh
```

If the cluster has no Gateway API implementation, the script stops and tells you
so. To let it install Envoy Gateway v1.8.2 for you — a **cluster-wide** change:

```bash
INSTALL_GATEWAY=1 ./run.sh
```

## What it does

1. **Applies a Gateway** ([`gateway.yaml`](gateway.yaml)) — a `GatewayClass` and
   a `Gateway` named `flint-gateway` in the namespace. Flint never creates a
   Gateway; it attaches `HTTPRoute`s to one you own.

2. **Deploys two versions** of the same model:

    ```bash
    flint deploy tinyllama --runtime ollama --version v1 -n flint-example-03 --wait
    flint deploy tinyllama --runtime ollama --version v2 -n flint-example-03 --wait
    ```

    Each version gets its own Deployment and Service (`tinyllama-v1`,
    `tinyllama-v2`). Those Services are the backends the split weighs.

3. **Walks the rollout**, sampling 200 requests through the Gateway after each
   step and reporting the observed split:

    ```bash
    flint route tinyllama --to v1           # baseline: 100% v1
    flint route tinyllama --canary 10 v2    # 90/10
    flint route tinyllama --canary 50 v2    # 50/50
    flint route tinyllama --to v2           # cutover: 100% v2
    ```

4. **Sends a real completion** through the Gateway to show it is serving, not
   just routing.

Expected output at the canary step:

```text
▸ Canary — 10% to v2
$ flint route tinyllama --canary 10 v2 -n flint-example-03
Routed tinyllama (host tinyllama.local):
  v1: 90%
  v2: 10%
  observed: v1  91%  v2   9%   (203 of 200 requests)   expected: v1 90% / v2 10%
```

## How the split is measured

Requests are counted from each version's pod logs as a delta across the sampling
window. Readiness probes hit the same endpoint, so the observed total runs a few
requests above `SAMPLES` and percentages land within a point or two of the
target. That is the noise floor, not a routing error.

Sample harder if you want tighter numbers:

```bash
SAMPLES=1000 ./run.sh
```

## Both versions serve the same weights here

The Ollama runtime pulls by *model name*, so `v1` and `v2` are the same
TinyLlama — this example is about the traffic mechanics, which are identical
regardless of what is behind each version.

In a real rollout the versions differ. With vLLM that is one flag:

```bash
flint deploy mistral --version v1 --runtime vllm \
  --hf-repo mistralai/Mistral-7B-Instruct-v0.2 --gpu 1 --wait
flint deploy mistral --version v2 --runtime vllm \
  --hf-repo mistralai/Mistral-7B-Instruct-v0.3 --gpu 1 --wait

flint route mistral --to v1
flint route mistral --canary 10 v2
```

## Rollback

The reason to canary is being able to undo it. v1 stays deployed and healthy
while it takes no traffic, so rolling back is one command with no rebuild, no
redeploy, and no cold start:

```bash
flint route tinyllama --to v1 -n flint-example-03
```

Retire the old version only once you trust the new one:

```bash
flint delete tinyllama --version v1 -n flint-example-03 --yes
```

## Sending your own traffic

The route matches the hostname `tinyllama.local` (`<model>.local` by default),
so requests must carry that `Host` header. With the script's port-forward still
up:

```bash
curl -H "Host: tinyllama.local" http://localhost:18083/api/tags
```

Use a real name you own with `--host`:

```bash
flint route tinyllama --to v2 --host chat.example.com -n flint-example-03
```

**A split that appears to do nothing is nearly always a `Host` mismatch.** Check
with `flint route tinyllama --show -n flint-example-03`.

## Cleanup

```bash
./run.sh cleanup
```

Deletes the model (and with it the HTTPRoute), the Gateway, the GatewayClass and
the namespace. Envoy Gateway is left installed — the command to remove it is
printed.

## Next

- [Traffic routing guide](https://flint-llm.github.io/flint/routing/) — how the
  HTTPRoute is built, and what v0.1 does not do yet
