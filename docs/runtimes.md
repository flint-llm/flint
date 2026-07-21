# Runtimes

A *runtime* is the server that actually loads the model and answers requests.
Flint deploys three, selected with `--runtime`, all speaking an
OpenAI-compatible API:

```bash
flint deploy mymodel --runtime vllm    # default
flint deploy mymodel --runtime ollama
flint deploy mymodel --runtime tgi
```

## Comparison

|  | **vLLM** (default) | **Ollama** | **TGI** |
|---|---|---|---|
| Hardware | GPU | CPU (GPU optional) | GPU |
| Best for | Production GPU serving, high throughput | Small models, CPU clusters, dev/CI | HuggingFace-native GPU serving |
| Model source | HuggingFace repo (`--hf-repo`) | [Ollama library](https://ollama.com/library) tag (the model name) | HuggingFace repo (`--hf-repo`) |
| Pinned image | `vllm/vllm-openai:v0.25.1` | `ollama/ollama:0.32.1` | `ghcr.io/huggingface/text-generation-inference:3.3.7` |
| Container port | 8080 | 11434 | 80 |
| Readiness probe | `/health` | `/api/tags` | `/health` |
| Weight storage | PVC, persists across restarts | `emptyDir`, re-pulled per pod | `emptyDir` (`/data`), re-pulled per pod |
| Gated models | `--hf-token-secret` | n/a | `--hf-token-secret` |

Each Service is exposed on port 80 regardless of runtime, so the endpoint
(`http://<model>-<version>.<ns>.svc.cluster.local/v1`) and traffic routing work
the same everywhere.

Image tags are pinned per runtime for reproducible deploys and bumped
deliberately. Override with `--image` when you need a specific build.

## vLLM

The default, and the right choice for GPU serving: continuous batching and
paged attention give it the best throughput of the three.

```bash
flint deploy mistral --runtime vllm \
  --hf-repo mistralai/Mistral-7B-Instruct-v0.3 \
  --gpu 1 --wait
```

- `--hf-repo` is what vLLM loads; the model name is the served name clients ask
  for.
- Weights download into a PVC mounted at `/weights` (`HF_HOME=/weights`), so a
  restarted pod does not re-download them.
- The PVC defaults to `ReadWriteOnce` and `50Gi`. For multiple replicas sharing
  one volume, use `--weights-access-mode ReadWriteMany` on a StorageClass that
  supports it (otherwise give each replica its own node-local volume).
- Gated or private repos: put the token in a Secret under key `token` and pass
  `--hf-token-secret <name>`.

```bash
kubectl -n flint create secret generic hf --from-literal=token=hf_xxx
flint deploy llama --runtime vllm --hf-repo meta-llama/Llama-3.1-8B-Instruct \
  --hf-token-secret hf --gpu 1 --wait
```

## Ollama

Serves on CPU, so it runs on any cluster — including `kind` — which makes it
the practical choice for development, CI, and small models.

```bash
flint deploy tinyllama --runtime ollama --wait
```

- The **model name is an Ollama tag**, not an HF repo: `tinyllama`,
  `llama3.2`, `qwen2.5:0.5b`. `--hf-repo` does not apply.
- An init container pulls the model into an `emptyDir` before the server
  starts, so readiness means "model loaded and ready to answer".
- That `emptyDir` is per-pod: every pod restart re-downloads the model. Fine
  for small models, painful for large ones.
- CPU inference is slow for anything big. Keep to a few billion parameters.

This is the same engine as [`flint serve`](quickstart-local.md), but in a pod
rather than on your laptop.

## TGI

HuggingFace's Text Generation Inference — a good fit if you already standardise
on HF tooling.

```bash
flint deploy falcon --runtime tgi \
  --hf-repo tiiuae/falcon-7b-instruct --gpu 1 --wait
```

- The model is passed as `MODEL_ID` and downloaded at startup into `/data`,
  which is ephemeral: expect a re-download on pod restart.
- GPU-oriented (CUDA image); like vLLM it needs `--gpu`.
- Supports `--hf-token-secret` for gated repos.

## Choosing

- **GPU cluster, production traffic** → vLLM.
- **No GPU, or a small model, or CI** → Ollama.
- **Already invested in HF serving** → TGI.
- **Just trying Flint on a laptop** → `flint serve` (local mode).

## Resources and scaling

Resource flags are runtime-independent:

```bash
flint deploy mymodel --runtime vllm --gpu 2 --gpu-type nvidia.com/gpu \
  --cpu-request 2000m --memory-request 16Gi --replicas 2 --wait
```

No HPA is created unless you pass `--hpa`, and that HPA is CPU-based — a poor
signal for GPU-bound inference. For GPU serving, prefer a fixed `--replicas`
count, or drive scaling from your own GPU/queue metrics.

## Adding a runtime

Runtimes are adapters behind a `RuntimeAdapter` protocol
(`flint/runtimes/base.py`): image, port, readiness probe, default resources,
plus a template directory holding the manifests. Implement the protocol,
register it in `flint/runtimes/registry.py`, and it becomes a valid
`--runtime` value. See
[CONTRIBUTING.md](https://github.com/flint-llm/flint/blob/main/CONTRIBUTING.md).
