# flint/core Coding Conventions

These are live invariants. Every session that adds or modifies code under
`flint/core/` must follow them. They exist because the monolith violated
each one, and the violations created real maintenance pain.

---

## 1. No dual-return pattern — return typed values, never dicts

**Old pattern:** Every monolith function checked a global `_http_mode` flag
and returned either `flask.jsonify(dict)` or the raw dict. Callers could
not trust the return type.

**Flint instead:** `flint/core/` functions return typed Python values
(Pydantic models, dataclasses, plain scalars, `None`). The CLI layer in
`flint/cli/` is responsible for formatting output for the user. There is
no `_http_mode`, no `jsonify`, no `{"status": "complete"}` dicts leaking
out of core modules.

**Why it matters:** Typed returns are checkable by mypy and testable without
an HTTP stack. Formatting concerns belong at the boundary, not inside
orchestration logic.

---

## 2. Wrap every kubernetes client call with `warnings.catch_warnings`

**Old pattern:** `_warnings.catch_warnings(simplefilter("ignore"))` was used
inconsistently — some k8s calls had it, others did not, causing spurious
`InsecureRequestWarning` noise in CLI output.

**Flint instead:** Every call to the kubernetes Python client must be wrapped:

```python
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    result = v1.list_pod_for_all_namespaces(watch=False)
```

This applies in `k8s_apply.py`, `cluster.py`, and any future module that
imports `kubernetes.client`.

**Why it matters:** The kubernetes client emits `InsecureRequestWarning`
against clusters without TLS verification. Wrapping consistently keeps CLI
output clean without globally silencing warnings.

---

## 3. Raise typed exceptions — no bare `except:`, no status dicts

**Old pattern:** The monolith used `except: pass` to swallow errors silently,
or returned `{"status": "incomplete", "error_message": "..."}` dicts that
callers had to inspect manually. Neither pattern is detectable by mypy or
testable cleanly.

**Flint instead:** Always raise a specific exception from `flint/core/errors.py`:

```python
# Wrong
try:
    do_thing()
except:
    pass

# Wrong
return {"status": "incomplete", "error_message": str(e)}

# Right
try:
    do_thing()
except SomeSpecificError as exc:
    raise K8sError(f"Useful message: {exc}") from exc
```

The CLI catches `FlintError` and formats it for the user. `--debug` lets
the raw traceback through.

**Why it matters:** Typed exceptions let callers distinguish error cases,
let mypy verify that errors are handled, and produce readable tracebacks in
`--debug` mode. Status dicts silently swallow context.

---

## 4. Use `logging`, not `print()`

**Old pattern:** The monolith used `print()` for all output — debugging,
progress, errors, and user messages were indistinguishable.

**Flint instead:** Every `flint/core/` module uses the standard library logger:

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Loading kubeconfig")
logger.info("Deployment ready: %s", deploy_name)
logger.warning("Pod not found: %s", service_name)
```

User-facing output (progress, results, prompts) belongs in `flint/cli/`
using `click.echo`. `flint/core/` modules must not `print()`.

**Why it matters:** `logging` is configurable (level, format, handlers)
without changing module code. Tests can capture log output via `caplog`.
`print()` statements in library code are untestable and pollute test output.
