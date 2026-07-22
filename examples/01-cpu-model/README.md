# 01 — A small model on CPU

Deploy TinyLlama to Kubernetes with the Ollama runtime, send it a request, read
its logs, and delete it. **No GPU required**, so this runs on any cluster —
including a `kind` cluster on your laptop.

- **Time:** ~10 minutes, most of it downloading the model
- **Needs:** a reachable cluster, `kubectl`, `flint`

## Run it

```bash
pip install flint-llm
./run.sh
```

Or against a throwaway namespace:

```bash
NAMESPACE=my-sandbox ./run.sh
```

No cluster? `kind create cluster --name flint-examples` (needs Docker).

## What it does

1. **Deploys** `tinyllama` on the Ollama runtime and waits for the rollout:

    ```bash
    flint deploy tinyllama --runtime ollama -n flint-example-01 --wait --wait-timeout 900
    ```

    This creates a Deployment and a ClusterIP Service named `tinyllama-latest`
    (`<model>-<version>`, version defaults to `latest`). No PVC: the Ollama
    runtime pulls into an `emptyDir`.

2. **Inspects** it with `flint status` and `flint list`.

3. **Calls it** through a `kubectl port-forward`, using the OpenAI-compatible
   `/v1/chat/completions` endpoint, and prints the model's answer.

4. **Reads logs** with `flint logs tinyllama --tail 10`.

The model keeps running afterwards so you can poke at it. Clean up with:

```bash
./run.sh cleanup
```

## Why the first run is slow

An init container pulls the model (~640 MB for TinyLlama) *before* the server
starts, so the pod only reports Ready once it can actually answer. That
`emptyDir` is per-pod: delete the pod and the next one downloads again. It is a
deliberate trade — fine for small models, which is exactly what this runtime is
for. See [Runtimes](https://flint-llm.github.io/flint/runtimes/).

## Things worth trying

```bash
# Preview the manifests without touching the cluster
flint deploy tinyllama --runtime ollama --dry-run

# Deploy is idempotent — re-run it and nothing churns
./run.sh

# Two replicas
flint deploy tinyllama --runtime ollama -n flint-example-01 --replicas 2 --wait
```

> **Note:** Ollama tags containing `.` or `:` (`llama3.2`, `qwen2.5:0.5b`)
> cannot be deployed in v0.1 — the model name becomes a Kubernetes resource
> name, which must be a DNS-1123 label. `tinyllama`, `phi3` and `gemma` are fine.

## Next

- [02-gpu-model](../02-gpu-model/) — a 7B model on GPU with vLLM
- [03-canary-rollout](../03-canary-rollout/) — two versions and a traffic split
