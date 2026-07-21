# Flint

Flint deploys and serves large language models on your own Kubernetes cluster —
or on your laptop — behind a single OpenAI-compatible endpoint.

It is a CLI, not a platform: it uses your existing kubeconfig and does all
orchestration client-side. There is no Flint server to install, no controller in
your cluster, and no state outside the Kubernetes objects it creates.

!!! warning "v0.1.0 — early (alpha) release"

    Interfaces may still change. Try Flint on a non-production cluster first.
    The GPU serving paths (vLLM, TGI) are best validated on your own hardware.

## Install

```bash
pip install flint-llm    # the distribution is flint-llm; the CLI command is `flint`
flint version            # -> flint 0.1.0
```

Python 3.12 or newer.

## Where to start

<div class="grid cards" markdown>

- **[Local quickstart](quickstart-local.md)** — serve a model on your laptop via
  Ollama in about three minutes. No cluster required.
- **[Kubernetes quickstart](quickstart-cluster.md)** — deploy a model to a
  cluster, check it, and tear it down in about ten minutes.
- **[Runtimes](runtimes.md)** — vLLM, Ollama, or TGI: what each is good at and
  how they differ.
- **[Traffic routing](routing.md)** — run two versions side by side and shift
  traffic between them with the Gateway API.

</div>

## What Flint does

| Command | What it does |
|---------|--------------|
| `flint serve` | Serve a model locally via Ollama, OpenAI-compatible. |
| `flint deploy` | Deploy a model to Kubernetes (Deployment/Service/PVC, optional HPA). |
| `flint status` | Replica readiness, endpoint, and current traffic split. |
| `flint list` | Every Flint-managed deployment in a namespace. |
| `flint logs` | Tail the runtime pod logs. |
| `flint route` | Shift traffic between deployed versions (canary or cutover). |
| `flint delete` | Tear a model down, all versions or one. |
| `flint init` | Scaffold a `flint.toml` with project defaults. |
| `flint version` | Print the installed version. |

Full options for every command are in the [CLI reference](cli.md).

## What Flint does not do

- **Build images.** Flint deploys published runtime images; it does not build
  containers for you.
- **Run a control plane.** Nothing of Flint runs in your cluster. If you delete
  the CLI, your deployments keep serving.
- **Own your Gateway.** Traffic routing writes an `HTTPRoute` against a Gateway
  you already run (for example [Envoy Gateway](https://gateway.envoyproxy.io)).

## License

Apache 2.0. Source at
[github.com/flint-llm/flint](https://github.com/flint-llm/flint).
