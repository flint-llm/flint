# Flint Architecture

**Version:** 0.1 (target)
**Status:** Design
**License:** Apache 2.0

---

## Design Principles

1. **Developer trust is the only concern.** No marketing features, no enterprise features, no multi-tenant anything in v0.1. Every design choice answers to: would a developer trust and enjoy using this?
2. **Narrow scope, ruthless.** Flint deploys LLMs to your own Kubernetes cluster and routes traffic between versions. That's it. Everything else is v0.2+ or someone else's tool.
3. **CLI-only, no server.** v0.1 has no control plane. The CLI uses the user's kubeconfig and does all orchestration client-side. Adding a server is a future decision driven by a concrete need (multi-user, scheduled builds, reconciliation) — not instinct.
4. **Opinionated defaults, escape hatches via flags.** Out of the box, `flint deploy <model>` does the right thing for 80% of cases. Power users override with `--` flags or raw template edits.
5. **Pluggable runtimes, not pluggable everything.** vLLM, Ollama, and TGI are first-class. The abstraction stops there. Bring-your-own-runtime is v0.2+.
6. **Template-driven, readable output.** Every Kubernetes resource Flint creates is rendered from a Jinja2 template the user can read and override. `flint deploy --dry-run` prints the YAML. No hidden magic.
7. **OpenAI-compatible by default.** Every deployment exposes `/v1/chat/completions` with SSE streaming. That's the contract.
8. **Apache 2.0, permanent.** No BSL, no SSPL, no dual-license games.

---

## System Modes

Flint runs in one of two modes.

**Local mode** — `flint serve <model>` runs Ollama as a subprocess on the developer's machine and exposes an OpenAI-compatible endpoint at `localhost:11434`. No cluster involved. For experimentation, prompt iteration, and onboarding.

**Cluster mode** — `flint deploy <model>` renders templates, pulls runtime images from the configured registry, applies Kubernetes manifests via the user's kubeconfig. No Flint server component. The CLI is the client; Kubernetes is the control plane.

Both modes share the same runtime abstraction and the same endpoint contract.

---

## High-Level Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Developer Machine                        │
│                                                             │
│   flint CLI (Python / Click)                                │
│   ├── Local mode       → Ollama subprocess → OpenAI API     │
│   └── Cluster mode     ↓                                    │
│                        │ kubeconfig                         │
└────────────────────────┼────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                       │
│                                                             │
│   Namespace: flint                                          │
│     ├── Deployment / Service    ← rendered from templates   │
│     ├── PVC (model weights)                                 │
│     ├── HPA                                                 │
│     └── HTTPRoute (Gateway API) ← traffic splits            │
│                                                             │
│   Runtime pods: vLLM │ Ollama │ TGI                         │
│     └── OpenAI-compatible /v1 endpoints                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### `flint` CLI
- Python 3.12+, Click, httpx, kubernetes client
- Commands: `init`, `serve`, `deploy`, `route`, `list`, `status`, `logs`, `delete`, `version`
- Reads config from `~/.config/flint/config.toml` and per-project `flint.toml`
- Uses the user's current kubeconfig context for all cluster operations

### Template Engine
- Jinja2 templates shipped inside the `flint` Python package
- Template families: deployment, service, pvc, hpa, httproute, servicemonitor (optional)
- Per-runtime overrides under `templates/runtimes/{vllm,ollama,tgi}/`
- `flint deploy --dry-run` prints rendered YAML; `--template-dir` swaps in user overrides

### Runtime Adapters
A runtime adapter is a small Python class that tells Flint:
- What container image to use
- What args and env vars the runtime needs
- What GPU resources to request
- What port to expose
- Where model weights live on disk
- How to probe readiness

Implementations in v0.1: `VLLMAdapter`, `OllamaAdapter`, `TGIAdapter`.

### Kubernetes Client Layer
Thin wrapper over the official `kubernetes` Python client. All cluster writes go through this. Supports dry-run, server-side apply (field manager `flint`), and structured error reporting.

### Registry Integration
v0.1 pulls prebuilt runtime images from vendor registries (e.g., `vllm/vllm-openai`, `ollama/ollama`, `ghcr.io/huggingface/text-generation-inference`). Model weights are pulled separately via HuggingFace Hub into a PVC. **Flint does not build container images in v0.1.** Custom model-baked images are a v0.2+ feature; if users need one, they build it with their own tooling and point Flint at it via `--image`.

---

## Key Flows

### `flint deploy llama-3.2 --runtime vllm`
1. Resolve the model reference (`llama-3.2` → HF model id or explicit image, per project config).
2. Select runtime adapter (`vllm`).
3. Render templates: Deployment, Service, PVC, HPA.
4. Weights: if PVC doesn't exist, create it. Prefetch via HuggingFace CLI in an init container.
5. Server-side apply via the Kubernetes Python client (field manager `flint`).
6. Poll pod readiness. Print progress.
7. On ready: print the in-cluster endpoint URL and an example curl command.

### `flint route llama-3.2 --canary 10 v2`
1. Look up the existing `HTTPRoute` for `llama-3.2`.
2. Verify `llama-3.2:v2` deployment exists and is ready.
3. Rewrite the HTTPRoute with two weighted backends (90/10).
4. Apply. Print the new split.

### `flint serve llama-3.2`
1. Check Ollama is on PATH; if missing, print install instructions and exit.
2. `ollama pull llama-3.2` if not already local (with progress).
3. `ollama serve` as a subprocess. Stream logs to stdout.
4. Print the local endpoint (`http://localhost:11434/v1`) and a curl example.

---

## Template System

All templates are Jinja2 files shipped inside the `flint` package. The template root is selectable; defaults can be overridden per project via `flint.toml`:

```toml
[templates]
dir = "./flint-templates"
```

Templates receive a single Pydantic-validated, versioned context object: model name, model version, runtime, image, GPU type and count, replica count, namespace, service account, resource limits, and runtime-specific extras. Context schema changes follow semver.

---

## Runtime Adapter Interface

```python
class RuntimeAdapter(Protocol):
    name: str

    def image(self, model: ModelRef) -> str: ...
    def args(self, model: ModelRef) -> list[str]: ...
    def env(self, model: ModelRef) -> dict[str, str]: ...
    def resources(self, model: ModelRef) -> ResourceSpec: ...
    def readiness_probe(self) -> Probe: ...
    def weights_strategy(self) -> WeightsStrategy: ...
```

New runtimes are added by subclassing. v0.1 ships three implementations. Third-party runtimes via plugin discovery are a v0.2+ consideration.

---

## Weights and Storage

- Weights cached on a `ReadWriteMany` PVC where the cluster supports it; otherwise per-pod.
- Default pull source: HuggingFace Hub. `HF_TOKEN` passed via a Kubernetes secret when the model is gated.
- Prefetch strategy: an init container downloads weights before the runtime container starts.
- Users can override with a pre-baked image (`--image`) or an existing NFS/CSI mount (`--weights-pvc`).

---

## Networking and Traffic

- **Service type:** `ClusterIP` by default. `LoadBalancer` or `NodePort` opt-in via flag.
- **Ingress:** Gateway API (`HTTPRoute`). v0.1 requires a Gateway API implementation in-cluster (Envoy Gateway, Istio, or Contour). If none is detected, Flint prints a clear error with install suggestions.
- **Traffic splits:** `HTTPRoute` with weighted `backendRefs`. `flint route` rewrites weights; it never touches the Service.
- **TLS:** out of scope for v0.1. Users terminate TLS at their existing gateway/ingress.
- **Streaming:** all three runtimes support SSE on `/v1/chat/completions` natively. Flint adds nothing here.

---

## Authentication

- **CLI → Kubernetes:** the user's kubeconfig. Whatever `kubectl` can do, `flint` can do.
- **Client → model endpoint:** none in v0.1. The deployed endpoint is unauthenticated inside the cluster. If exposed externally, the user handles auth at their gateway.
- **No Flint-native auth, no user system, no RBAC layer beyond Kubernetes RBAC.** Explicit v0.1 choice.

---

## Observability

- **Logs:** `flint logs <model>` tails runtime pod stdout via the Kubernetes API.
- **Metrics:** runtime pods expose Prometheus metrics on `/metrics` (vLLM and TGI natively). Flint optionally creates a `ServiceMonitor` when the `monitoring.coreos.com` API is present.
- **Traces:** out of scope for v0.1.
- **Dashboard:** out of scope for v0.1. k9s, Lens, Headlamp, and Grafana cover this.

---

## Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Salvageable code is Python; ecosystem fits K8s + ML |
| CLI framework | Click | Already in cli-client; good UX |
| K8s client | `kubernetes` (official) | Well-maintained, server-side apply support |
| Template engine | Jinja2 | 120+ existing templates to port |
| HTTP client | httpx | Async-capable, modern |
| Config format | TOML | Python-native, unambiguous |
| Validation | Pydantic v2 | Strong typing for template context |
| Traffic management | Gateway API (`HTTPRoute`) | Vendor-neutral, CNCF direction |
| Local runtime | Ollama | Best dev UX for local LLMs |
| Cluster runtimes | vLLM, Ollama, TGI | Covers the common choices |
| Lint/format | `ruff` | Fast, one tool |
| Type check | `mypy --strict` on `flint/core/` | Library code strict, CLI handlers relaxed |
| Tests | `pytest` + `kind` for integration | Real Kubernetes for integration |
| CI | GitHub Actions | Standard |
| Docs | MkDocs Material | Good defaults, GitHub Pages friendly |

---

## Repository Layout

```
flint/
├── flint/                        # Python package
│   ├── cli/                      # Click commands
│   ├── core/                     # Orchestration logic (ex-cli_dataspine.py)
│   ├── runtimes/                 # Runtime adapters
│   ├── k8s/                      # Kubernetes client wrapper
│   ├── templates/                # Jinja2 templates
│   └── config/                   # Config loading
├── tests/
│   ├── unit/
│   └── integration/              # runs against kind
├── docs/                         # MkDocs site
├── examples/                     # worked examples
├── .github/workflows/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE                       # Apache 2.0
├── SECURITY.md
└── CONTRIBUTING.md
```

Single repo, single package, single language for v0.1.

---

## Non-goals for v0.1

Stated explicitly to resist scope creep. Each of these is a reasonable feature; none belong in v0.1.

- No Flint server or control plane
- No custom authentication, user accounts, or RBAC layer
- No web dashboard
- No Jupyter integration
- No fine-tuning support
- No training pipelines
- No multi-tenant isolation primitives
- No prompt management, versioning, or A/B testing UI
- No token usage or cost tracking
- No managed or hosted offering
- No non-LLM model support (classical ML, embeddings-only, vision — though vLLM covers many of these if users opt in)
- No CRDs or Kubernetes operator
- No custom scheduler or autoscaler
- No TLS termination or certificate management
- No built-in observability dashboard
- No container image building (use your own `docker buildx` + registry)
- No Windows support for local mode (macOS + Linux only)
