# Flint Build Plan

**Target:** v0.1.0
**Working model:** Session-based. Sessions are scope units, not time units. Each session has a goal, scope, non-goals, and exit criteria. A session is not complete until every exit criterion is verifiably met. The next session does not start before the current one is complete.

---

## Conventions

- Each session produces something mergeable to `main`, behind a feature flag or release tag where appropriate.
- **"Demo-able"** = a fresh developer following the README can reproduce the behaviour.
- **"Tested"** = unit and integration tests are added and CI is green.
- **`kind`** (Kubernetes in Docker) is the reference cluster for integration tests.
- A real GPU cluster is tested manually at the end of each cluster-touching session.
- Exit criteria are binary: met or not met. No "partially met."

---

## Session Map

| # | Session | Outcome |
|---|---|---|
| S0 | Foundation | Clean public repo, CI, salvaged code copied in |
| S1 | Extract orchestration logic | Monolith decomposed into typed, tested modules |
| S2 | Local mode | `flint serve` works via Ollama |
| S3 | Cluster deploy (vLLM) | `flint deploy` happy path on Kubernetes |
| S4 | Multi-runtime support | Ollama and TGI join vLLM |
| S5 | Traffic routing | `flint route` with Gateway API |
| S6 | Operational CLI | `logs`, `status`, `list`, `delete`, solid errors |
| S7 | v0.1.0 launch | PyPI, docs, examples, public announcement |

---

## S0 — Foundation

**Goal:** A new public `flint` repo exists with clean history, Apache 2.0 license, working CI, and the code we plan to salvage copied in — not yet refactored.

**In scope**
- Create the new `flint` GitHub repository, Apache 2.0
- Copy from `api-server` (no git history): `cli_dataspine.py`, the 120+ Jinja2 templates, the Flask wrapper as reference
- Copy from `cli-client` (no git history): the Click command skeleton
- Set up `pyproject.toml` with Python 3.12+, core deps, dev deps
- Configure `ruff`, `mypy`, `pytest`, `pre-commit`
- GitHub Actions: lint + typecheck + test on PR and on push to `main`
- Add stub `README.md` ("v0.1 in development"), `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- Archive all legacy Dataspine repos as private. None made public in this session.

**Non-goals**
- Secret-scrubbing old repos (no value if they stay private)
- Refactoring any copied code
- Implementing new features
- Publishing to PyPI

**Exit criteria**
1. `github.com/<org>/flint` exists, is public, licensed Apache 2.0
2. All legacy Dataspine repos on GitHub are set to private and marked as archived
3. `pip install -e ".[dev]"` succeeds in a fresh Python 3.12 venv
4. `pytest` runs and passes (empty suite is acceptable)
5. `ruff check .` exits 0
6. `mypy flint` exits 0 (initial mypy config may be permissive; strictness tightens in S1)
7. CI is green on a trivial PR
8. `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md` are present and non-empty

---

## S1 — Extract the orchestration logic

**Goal:** The 4,777-line `cli_dataspine.py` is decomposed into clean Python modules with clear boundaries, typed interfaces, and enough tests to refactor further with confidence.

**In scope**
- Identify the distinct concerns in the monolith: model metadata, template rendering, Kubernetes apply, build/push, logs, traffic routing, cluster introspection
- Split into modules under `flint/core/`: `models.py`, `templates.py`, `k8s_apply.py`, `build.py`, `logs.py`, `routing.py`, `cluster.py`
- Introduce typed Pydantic v2 models for the template rendering context
- Keep all existing Jinja2 templates under `flint/templates/`; verify each renders against a synthetic context
- Add unit tests for each module's pure functions (template rendering, metadata parsing, resource spec construction)
- Remove dead code: the commented-out `cluster.py` in cli-client, Python 2 artifacts, the `pdb` import, bare `except: pass` blocks, Python 2 `print` statements

**Non-goals**
- Any new functionality
- Runtime adapter abstraction (S4)
- CLI polish
- Integration tests against a real cluster

**Exit criteria**
1. `cli_dataspine.py` no longer exists as a single file; all logic lives in named modules under `flint/core/`
2. Every public function in `flint/core/` has a full type signature
3. `mypy --strict flint/core/` exits 0
4. Unit test coverage of `flint/core/` is ≥ 70% (measured with `coverage.py`)
5. All 120+ Jinja2 templates render with a valid context without error (snapshot-tested)
6. Zero occurrences of `import pdb`, bare `except:`, `print(` used for logging, or Python 2 `print` statements anywhere in `flint/`
7. CI remains green

---

## S2 — Local mode

**Goal:** `flint serve <model>` works. A developer with Ollama installed runs one command and gets an OpenAI-compatible endpoint serving a model on their machine.

**In scope**
- `flint serve <model>` command
- Detect Ollama on PATH; if missing, print install instructions and exit with a useful error
- `ollama pull <model>` if not already local, with progress
- `ollama serve` as subprocess; stream logs; handle Ctrl+C cleanly
- Print the local endpoint URL and an example `curl` command on startup
- `flint version` and `flint init` (scaffold a `flint.toml`) ship in this session
- E2E test: `flint serve tinyllama` (or smallest practical model) in CI, hit `/v1/chat/completions`, verify a streamed response

**Non-goals**
- Any Kubernetes interaction
- Docker-based serving
- Runtimes other than Ollama in local mode

**Exit criteria**
1. `flint serve tinyllama` on a dev machine with Ollama installed starts a server within 60 seconds, excluding model download
2. `curl -N http://localhost:11434/v1/chat/completions ...` returns a valid streamed SSE response
3. Ctrl+C cleanly stops the subprocess; no zombie processes on macOS or Linux
4. `flint serve` with no Ollama installed prints a readable error with install guidance
5. CI runs the E2E test end-to-end against a pinned small model
6. `flint init` produces a valid `flint.toml` that `flint serve` can read

---

## S3 — Cluster deploy (vLLM, one happy path)

**Goal:** `flint deploy <model>` deploys a vLLM-served model to a Kubernetes cluster using the user's current kubeconfig context. Works on `kind` in CI (CPU-only, tiny model) and on a real GPU cluster when tested manually.

**In scope**
- `flint deploy <model>` with vLLM as the default runtime
- Template rendering: Deployment, Service, PVC, HPA
- Server-side apply via the Kubernetes Python client, field manager `flint`
- Readiness polling with clear progress output
- Weight prefetch via HuggingFace CLI in an init container
- `--dry-run` prints rendered YAML without applying
- `--namespace` flag; default namespace is `flint`, created if missing
- Sensible GPU resource defaults (`nvidia.com/gpu: 1`), overridable via flag
- Integration test: deploy a CPU-friendly model (e.g., `facebook/opt-125m`) to `kind`, hit `/v1/chat/completions`, assert on the response

**Non-goals**
- Ollama or TGI runtimes (S4)
- Traffic splitting (S5)
- `logs` and `status` commands (S6)
- User-supplied custom container images — only stock runtime images in v0.1

**Exit criteria**
1. `flint deploy <model>` against a fresh `kind` cluster produces a Ready pod within 5 minutes (small model)
2. The deployed pod serves `/v1/chat/completions` with a valid streamed response
3. `flint deploy --dry-run` prints valid YAML; applying that YAML with `kubectl apply` produces an equivalent deployment
4. Deploying twice with identical args is idempotent: `kubectl diff` returns clean; no resource churn
5. A real GPU cluster manual test with `meta-llama/Llama-3.2-1B` (or similar) succeeds
6. Integration test in CI passes against `kind`

---

## S4 — Multi-runtime support

**Goal:** The runtime adapter abstraction is formalized. Ollama and TGI join vLLM as first-class cluster-deployable runtimes.

**In scope**
- Formalize `RuntimeAdapter` protocol in `flint/runtimes/base.py`
- Refactor S3's vLLM path to implement the adapter
- Add `OllamaAdapter` and `TGIAdapter`
- `flint deploy --runtime {vllm,ollama,tgi}` flag
- Per-runtime templates where needed, under `templates/runtimes/{vllm,ollama,tgi}/`
- Per-runtime default resource specs and readiness probe endpoints
- Integration tests for each runtime against `kind` (CPU-friendly model where possible)
- Docs page: runtime comparison table, when to use which

**Non-goals**
- Third-party / bring-your-own runtimes
- Automatic runtime selection from model metadata (v0.2+)

**Exit criteria**
1. `flint deploy <model> --runtime <r>` succeeds for all three runtimes against `kind`
2. Each deployed runtime exposes `/v1/chat/completions` correctly
3. The `RuntimeAdapter` protocol is documented in a "how to add a runtime" page, even though it is not yet a supported extension point
4. No vLLM-specific code remains outside `flint/runtimes/vllm/`
5. CI runs integration tests for all three runtimes and passes

---

## S5 — Traffic routing

**Goal:** `flint route` manages traffic splits between model versions using the Gateway API. Canary patterns work end-to-end.

**In scope**
- `flint route <model> --canary <pct> <version>` — weighted split
- `flint route <model> --to <version>` — full cutover
- `flint route <model> --show` — print current split
- `HTTPRoute` rendering and server-side apply
- Detection of a Gateway API implementation in the cluster; clear error if missing, with install pointers
- Docs: list of tested Gateway API implementations (Envoy Gateway first, Istio second)
- Integration test: two versions deployed, route 50/50, send many requests, verify both versions receive traffic within tolerance

**Non-goals**
- Shadow routing (v0.2 — Gateway API mirror support is uneven)
- Header-based A/B routing
- Automated progressive rollout (flagger-style)

**Exit criteria**
1. Two versions of a model can be deployed side by side (e.g., `flint deploy <model>:v1` and `<model>:v2`)
2. `flint route <model> --canary 10 v2` splits traffic 90/10; verified by request counts within ±3% over 1000 requests
3. `flint route <model> --to v2` fully cuts over; no requests returned from v1 after the cutover completes
4. `flint route <model> --show` prints current weights accurately
5. Missing Gateway API produces an actionable error naming specific install options
6. CI runs the integration test against `kind` + Envoy Gateway

---

## S6 — Operational CLI

**Goal:** The day-2 commands a developer actually needs — logs, status, list, delete — with readable errors and idempotent behaviour.

**In scope**
- `flint list` — all Flint-managed deployments in the current namespace
- `flint status <model>` — pod status, replica counts, route weights, endpoint URL
- `flint logs <model> [--follow] [--since]` — tail runtime pod logs
- `flint delete <model>` — remove Deployment, Service, HPA, PVC; `--keep-weights` preserves the PVC
- Error-handling pass: every error the CLI produces is readable and actionable; no raw Python tracebacks unless `--debug`
- Retry/backoff on transient Kubernetes API errors
- `--verbose` and `--debug` flags wired consistently across commands
- Unit tests for error formatting
- Docs: "common errors" page

**Non-goals**
- `flint exec` (k9s covers this)
- Metrics or dashboard commands
- Shell completion polish (nice-to-have, can slip to S7)

**Exit criteria**
1. `flint list`, `status`, `logs`, `delete` are implemented and covered by integration tests
2. No code path in the CLI emits a raw Python traceback without `--debug`
3. `flint delete` followed by `flint deploy` with identical args leaves the cluster in the same state as a fresh deploy
4. Running any command with no cluster access produces a readable error, not a traceback
5. Docs include a "troubleshooting" page covering the 10 most likely errors and their resolutions

---

## S7 — v0.1.0 launch

**Goal:** Flint 0.1.0 is installable, documented, and publicly launched. A developer discovering the project can go from zero to a deployed model in under 10 minutes.

**In scope**
- Publish to PyPI
- Homebrew tap (can defer if tight on time)
- Docs site: MkDocs Material on GitHub Pages
  - Quickstart (local mode, 3 minutes)
  - Quickstart (cluster mode, 10 minutes)
  - CLI reference (auto-generated from Click)
  - Runtime comparison
  - Traffic routing guide
  - Troubleshooting
- 3 worked examples in `examples/`: small CPU model, medium GPU model, canary rollout
- Release process: version tagging, CHANGELOG, GitHub Release with notes
- Launch README: what Flint does in 2 sentences, install, 60-second demo, link to docs
- Demo video or asciinema cast, 60 seconds, terminal only
- Public announcement (HN, Reddit, Mastodon, wherever fits)

**Non-goals**
- Helm chart for Flint (there is no server to install in v0.1)
- Marketing site beyond the docs
- Non-English documentation

**Exit criteria**
1. `pip install <package-name>` from a clean environment produces a working `flint` binary
2. The cluster-mode quickstart in the docs, executed verbatim by a developer who has never seen Flint before, successfully deploys a model in under 10 minutes (verified with one external person)
3. `flint --help` is readable and consistent across all commands
4. GitHub Release for v0.1.0 is tagged, with wheel artifacts and a CHANGELOG entry
5. Docs site is live and linked from the README
6. 3 end-to-end examples in `examples/` are reproducible from the directory
7. Public announcement is posted

---

## Open questions to resolve during the build

These are intentionally left open; decisions happen at the session where they bite.

- **Final package name on PyPI.** `flint` is likely taken; `flint-cli` or `flintctl` are plausible fallbacks. Decide by S7.
- **Reference Gateway API implementation.** Envoy Gateway is the current preference; revisit during S5 based on `kind` integration experience.
- **Minimum Kubernetes version.** Tentatively 1.28 (Gateway API `v1` is GA). Pin in S3.
- **Whether to include a bundled Prometheus ServiceMonitor by default or opt-in.** Decide in S6 after seeing what the runtime pods emit out of the box.
