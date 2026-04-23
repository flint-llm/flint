# Flint — Claude Code Guide

## Project overview

Flint is a Python CLI that deploys LLMs to Kubernetes and routes traffic between versions. No Flint server; the CLI uses the user's kubeconfig and does all orchestration client-side.

See `../FLINT_ARCHITECTURE.md` and `../FLINT_BUILD_PLAN.md` for full context.

## Repository layout

```
flint/                        Python package root (also the git repo root)
├── flint/                    Python package
│   ├── cli/                  Click commands (empty until S2)
│   ├── core/                 Orchestration logic (extracted from monolith in S1)
│   │   ├── errors.py         FlintError hierarchy
│   │   ├── models.py         Pydantic v2 domain types + utility functions
│   │   ├── templates.py      Jinja2 rendering engine
│   │   ├── k8s_apply.py      kubectl/k8s client wrappers
│   │   ├── cluster.py        Cluster introspection
│   │   ├── logs.py           Pod log retrieval
│   │   ├── routing.py        Traffic split management
│   │   └── build.py          Image pull/push
│   ├── runtimes/             Runtime adapters (empty until S4)
│   ├── k8s/                  (empty, reserved)
│   ├── config/               (empty, reserved)
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
- **CLI modules stay empty until S2**. Don't add logic to `flint/cli/`.
- **Runtime adapters empty until S4**. Don't add to `flint/runtimes/`.
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
| S2 | Not started | `flint serve` via Ollama |
| S3 | Not started | `flint deploy` via vLLM on Kubernetes |
| S4-S7 | Not started | See FLINT_BUILD_PLAN.md |

## Key TODOs left in code

| Location | TODO |
|----------|------|
| `k8s_apply.py` | TODO(S3): Migrate write ops to server-side apply via Python k8s client |
| `cluster.py` | TODO(S5): Replace Ingress/Istio lookups with Gateway API HTTPRoute |
| `routing.py` | TODO(S5): Render HTTPRoute instead of Istio RouteRules |
| `templates/vllm/*.j2` | TODO(S3): Pin specific vLLM image tags; tune resource defaults |
