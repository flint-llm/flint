# Quickstart — Kubernetes (10 minutes)

Deploy a model to a cluster, send it traffic, and tear it down. Flint uses your
current kubeconfig context and applies plain Kubernetes objects — there is
nothing to install in the cluster first.

## Prerequisites

- Python 3.12+ and `pip install flint-llm`
- A Kubernetes cluster (1.28+) reachable from your kubeconfig:

    ```bash
    kubectl config current-context     # this is the cluster Flint will use
    ```

- Permission to create Deployments, Services, PVCs and Namespaces
- **For vLLM or TGI:** GPU nodes with the NVIDIA device plugin installed, so
  pods can request `nvidia.com/gpu`

!!! tip "No GPU?"

    Use `--runtime ollama`, which serves on CPU. Every step below works the
    same way; just expect slower tokens. A `kind` cluster is enough.

## 1. Deploy

=== "GPU (vLLM)"

    ```bash
    flint deploy mistral --runtime vllm \
      --hf-repo mistralai/Mistral-7B-Instruct-v0.3 \
      --gpu 1 --wait
    ```

=== "CPU (Ollama)"

    ```bash
    flint deploy tinyllama --runtime ollama --wait
    ```

```text
Deployed mistral:latest to namespace flint
  manifests applied: 3
  endpoint: http://mistral-latest.flint.svc.cluster.local/v1
  rollout: ready
```

What that created, all labelled `flint.dev/managed=true`:

- a **Deployment** running the runtime image (pinned per runtime),
- a **Service** (ClusterIP, port 80) named `<model>-<version>`,
- a **PersistentVolumeClaim** for weights when the runtime downloads from
  HuggingFace Hub (vLLM), and
- optionally a **HorizontalPodAutoscaler** with `--hpa`.

Useful flags:

| Flag | Why |
|------|-----|
| `--dry-run` | Print the rendered manifests without applying anything. |
| `--version v2` | Tag this deployment (default `latest`); versions coexist. |
| `-n, --namespace` | Deploy somewhere other than `flint` (created if missing). |
| `--replicas 3` | More than one replica. |
| `--hf-token-secret hf` | Read a gated repo's token from a Secret (key: `token`). |
| `--wait-timeout 1200` | Large models can take a while to pull weights. |

The full list is in the [CLI reference](cli.md#flint-deploy).

!!! note "First deploy is slow"

    The runtime image is several GB and model weights are downloaded on first
    start. `--wait` (the default) blocks until the rollout is ready and prints
    progress; if it times out, the deploy is still running — watch it with
    `flint logs <model> --follow`.

## 2. Check it

```bash
flint status mistral       # replicas, readiness, endpoint, traffic split
flint list                 # every flint-managed model in the namespace
flint logs mistral --follow
```

## 3. Send a request

The Service is ClusterIP, so from outside the cluster the quickest path is a
port-forward:

```bash
kubectl -n flint port-forward svc/mistral-latest 8000:80
```

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral","messages":[{"role":"user","content":"Hello!"}]}'
```

From inside the cluster, use the endpoint Flint printed:
`http://mistral-latest.flint.svc.cluster.local/v1`.

For a stable external address across versions, put a Gateway in front and let
Flint manage the route — see [Traffic routing](routing.md).

## 4. Tear down

```bash
flint delete mistral               # all versions: Deployment/Service/HPA/PVC + HTTPRoute
flint delete mistral --version v2  # just one version
flint delete mistral --keep-weights
```

`delete` prompts before removing anything; `--yes` skips the prompt. It is
idempotent — deleting what is already gone is not an error.

## Troubleshooting

Deploy never becomes ready, pods pending, image pull errors — see
[Troubleshooting](troubleshooting.md). Re-run any command with `--verbose` for
INFO logs or `--debug` for full tracebacks.
