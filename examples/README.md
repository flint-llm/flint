# Examples

Three worked, end-to-end examples. Each directory is self-contained: `cd` into
it, read its `README.md`, run `./run.sh`, and `./run.sh cleanup` when you're
done.

| Example | Needs | Time | What it shows |
|---------|-------|------|---------------|
| [01-cpu-model](01-cpu-model/) | Any cluster (kind is fine) — **no GPU** | ~10 min | Deploy a small model on CPU with the Ollama runtime, call it, read its logs, delete it. |
| [02-gpu-model](02-gpu-model/) | GPU nodes + `nvidia.com/gpu` | ~20 min | Deploy a 7B model on vLLM with persistent weights, a HF token for gated repos, and multiple replicas. |
| [03-canary-rollout](03-canary-rollout/) | Any cluster + Envoy Gateway — **no GPU** | ~15 min | Run two versions side by side and shift traffic 100/0 → 90/10 → 50/50 → 0/100, measuring the actual split. |

Start with **01** if you have never run Flint against a cluster. **03** is the
interesting one — it is the reason Flint exists.

## Before you start

```bash
pip install flint-llm
flint version
kubectl config current-context     # the cluster every example will use
```

Every example takes a `NAMESPACE` environment variable if you want to keep
things apart from your other work:

```bash
NAMESPACE=my-sandbox ./run.sh
```

Each script is idempotent — re-running it re-applies the same objects rather
than creating duplicates — and each ends by printing the exact cleanup command.

## No cluster handy?

`kind` gives you one on your laptop with Docker:

```bash
kind create cluster --name flint-examples
```

Examples 01 and 03 run on it as-is. Example 02 needs real GPUs.

When you're finished with everything:

```bash
kind delete cluster --name flint-examples
```
