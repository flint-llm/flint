# Flint — development guide

## Project overview

Flint is a Python CLI that deploys LLMs to Kubernetes and routes traffic between versions. No Flint server; the CLI uses the user's kubeconfig and does all orchestration client-side.

See `build_docs/FLINT_ARCHITECTURE.md` and `build_docs/FLINT_BUILD_PLAN.md`
(kept local, not published) for full context.

## Repository layout

```
flint/                        Python package root (also the git repo root)
├── flint/                    Python package
│   ├── cli/                  Click commands
│   │   ├── main.py           `flint` group entrypoint
│   │   ├── version.py        `flint version`
│   │   ├── init.py           `flint init`
│   │   ├── serve.py          `flint serve` (local Ollama mode)
│   │   └── _errors.py        FlintError → click error formatting
│   ├── core/                 Orchestration logic
│   │   ├── errors.py         FlintError hierarchy (+ OllamaError subtypes)
│   │   ├── models.py         Pydantic v2 domain types + utility functions
│   │   ├── templates.py      Jinja2 rendering engine
│   │   ├── k8s_apply.py      kubectl/k8s client wrappers
│   │   ├── cluster.py        Cluster introspection
│   │   ├── logs.py           Pod log retrieval
│   │   ├── routing.py        Traffic split management
│   │   ├── build.py          Image pull/push
│   │   └── runtimes/
│   │       └── ollama_local.py  Local Ollama subprocess wrapper
│   ├── runtimes/             K8s runtime adapters (base + vllm/ollama/tgi)
│   ├── k8s/                  (empty, reserved)
│   ├── config/               flint.toml loader
│   └── templates/            Jinja2 templates shipped with package
│       └── vllm/             vLLM deployment/service/hpa/pvc templates
├── tests/
│   ├── unit/                 Unit tests (no cluster required)
│   └── integration/          Integration tests against kind (S3+)
├── _salvage/                 Legacy Dataspine code (reference only, DECOMMISSIONED)
│   ├── monolith.py           Original 4,777-line monolith
│   ├── api_server.py         Flask wrapper (reference)
│   ├── cli_legacy/           Old Click skeleton
│   └── templates/            Old Dataspine/Istio templates (not used by Flint)
├── pyproject.toml
├── mypy.ini
├── .ruff.toml
└── .pre-commit-config.yaml
```

## Development commands

```bash
pip install -e ".[dev]"       # install with dev deps
ruff check .                  # lint (excludes _salvage/)
mypy flint                    # type check (strict on flint/core/)
pytest                        # run all tests
pytest --cov=flint/core --cov-report=term-missing   # with coverage
```

## Architecture constraints

- **No Docker image builds** in v0.1. `build.py` only does pull/push.
- **No Flint server** — CLI only; uses user's kubeconfig.
- **No imports from `_salvage/`** from any `flint/` module.

## Code standards

- `flint/core/` is mypy strict (`strict = True` in mypy.ini).
- No `print()` for logging — use `logging.getLogger(__name__)`.
- No bare `except:` — always catch specific exception types.
- No `import pdb`.
- All public functions in `flint/core/` need full type annotations.
- See `flint/core/CONVENTIONS.md` for the full set of live coding invariants.

## Session state

| Session | Status | Notes |
|---------|--------|-------|
| S0 | Complete | Repo at github.com/flint-llm/flint, CI green |
| S1 | Complete | Monolith decomposed into 8 typed modules; CONVENTIONS.md + MONOLITH_MAP.md added |
| S2 | Complete | `flint version`, `flint init`, `flint serve` (local Ollama mode) |
| S3 | Complete | `flint deploy` + `flint status` (vLLM on Kubernetes); writes via Python-client server-side apply |
| S4 | Complete | `RuntimeAdapter` + vllm/ollama/tgi adapters; `flint deploy --runtime` |
| S5 | Complete | `flint route` (Gateway API HTTPRoute): `--to`, `--canary`, `--show` |
| S6 | Complete | `flint list`, `flint delete`, `flint logs`; error-handling pass |
| S7 | In progress | 0.1.0 on PyPI, docs site live, examples/ done; announce remains |

## Running the CLI

```bash
flint --help                          # lists all commands
flint version                         # prints installed version
flint init                            # scaffolds flint.toml in current dir
flint init --force                    # overwrites existing flint.toml
flint serve tinyllama                 # start local Ollama server (requires ollama on PATH)
flint serve tinyllama --port 12000    # use non-default port
```

E2E test (requires Ollama installed + tinyllama pulled):
```bash
FLINT_E2E_OLLAMA=1 pytest tests/integration/test_serve_local.py -v
```

## Key TODOs left in code

| Location | TODO |
|----------|------|
| `cluster.py` | TODO(S5): Replace remaining Ingress/Istio lookups with Gateway API (3 sites) |
