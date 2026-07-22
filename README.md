# Flint

Deploy and serve large language models on your own Kubernetes cluster — or on
your laptop — behind a single OpenAI-compatible endpoint. Flint is a CLI that
uses your existing kubeconfig and does all orchestration client-side; there is
no Flint server to run.

> **v0.1.0 — early (alpha) release.** Interfaces may still change; try it on a
> non-production cluster first. The GPU serving paths (vLLM, TGI) are best
> validated on your own hardware.

## Install

```bash
pip install flint-llm    # the distribution is flint-llm; the CLI command is `flint`
flint version            # -> flint 0.1.0
```

## Quickstart — local (~1 minute, no cluster)

Serve a model on your machine via [Ollama](https://ollama.com), OpenAI-compatible:

```bash
flint serve tinyllama
# -> Endpoint: http://localhost:11434/v1   (Ctrl+C to stop)
```

Point any OpenAI client at it — for example, the `openai` SDK with
`base_url="http://localhost:11434/v1"`, or curl:

```bash
curl -N http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"tinyllama","stream":true,
       "messages":[{"role":"user","content":"Say hi in one word."}]}'
```

## Deploy to Kubernetes

With a cluster in your kubeconfig (GPU nodes for vLLM/TGI):

```bash
flint deploy mistral --runtime vllm \
  --hf-repo mistralai/Mistral-7B-Instruct-v0.3 --gpu 1 --wait

flint status mistral            # replicas, readiness, endpoint, traffic split
flint logs mistral --follow     # tail the runtime pod logs
flint list                      # all flint-managed deployments
flint delete mistral            # tear down (Deployment/Service/HPA/PVC + route)
```

- **Preview first:** `flint deploy mistral --dry-run` prints the manifests without applying.
- **Runtimes:** `vllm` (default, GPU), `ollama` (CPU-capable), `tgi` (GPU) — via `--runtime`.

### Route traffic between versions

Deploy a second version, then shift traffic with the Gateway API (requires a
Gateway API implementation, e.g. Envoy Gateway):

```bash
flint route mistral --to v1           # 100% to v1 (baseline)
flint route mistral --canary 10 v2    # 90/10 canary
flint route mistral --show            # current split
```

## Commands

`deploy` · `status` · `list` · `logs` · `delete` · `route` · `serve` · `init` · `version`

Run `flint <command> --help` for options. Add `--debug` for full tracebacks,
`--verbose` for INFO logging.

## Examples

Three runnable, end-to-end examples in [`examples/`](examples/) — `cd` in and
run `./run.sh`:

| Example | Needs | Shows |
|---------|-------|-------|
| [01-cpu-model](examples/01-cpu-model/) | any cluster, no GPU | deploy a small model on CPU, call it, read logs |
| [02-gpu-model](examples/02-gpu-model/) | GPU nodes | a 7B model on vLLM with persistent weights |
| [03-canary-rollout](examples/03-canary-rollout/) | any cluster + Envoy Gateway | shift traffic 100/0 → 90/10 → 50/50 → 0/100 and measure it |

## Docs

**[flint-llm.github.io/flint](https://flint-llm.github.io/flint/)** — quickstarts
(local + cluster), runtime comparison, traffic-routing guide, full CLI reference.

- [Local quickstart](https://flint-llm.github.io/flint/quickstart-local/) — 3 minutes, no cluster
- [Kubernetes quickstart](https://flint-llm.github.io/flint/quickstart-cluster/) — 10 minutes
- [Troubleshooting](docs/troubleshooting.md) — common errors and fixes
- [CHANGELOG](CHANGELOG.md) — what's in each release

## License

Apache 2.0. See [LICENSE](LICENSE).
