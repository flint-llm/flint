# Troubleshooting

Common errors from the `flint` CLI and how to resolve them. Re-run any command
with `--debug` for a full traceback, or `--verbose` for INFO-level logs.

| # | Symptom | Cause | Resolution |
|---|---------|-------|------------|
| 1 | `Error: Failed to load kubeconfig: ...` | No reachable cluster / kubeconfig | Check `kubectl config current-context`; set `KUBECONFIG` or run against a live cluster. |
| 2 | `Error: Unsupported runtime '<x>'. Supported: ollama, tgi, vllm` | `--runtime` value has no adapter | Use one of `vllm`, `ollama`, `tgi`. |
| 3 | `Error: No model specified. Pass MODEL or set [defaults].model in flint.toml` | `flint deploy` with no model | Pass a model name, or set `[defaults].model` in `flint.toml`. |
| 4 | `Error: No manifests were rendered for runtime '<x>'` | Runtime has no deploy templates | Only cluster runtimes (vllm/ollama/tgi) are deployable; `ollama` local mode is `flint serve`. |
| 5 | `Error: Gateway API is not installed in this cluster ...` | `flint route` without a Gateway API implementation | Install Envoy Gateway (link in the error) or the Gateway API CRDs. |
| 6 | `Error: No baseline version to canary against ...` | `--canary` with no existing route | Establish a baseline first: `flint route <model> --to <version>`. |
| 7 | `Error: Canary requires a single baseline version ...` | Split already spans multiple versions | Consolidate first with `flint route <model> --to <version>`. |
| 8 | `Error: No pods found for model '<m>' in namespace '<ns>'` (`flint logs`) | Model not deployed, wrong namespace, or pod not scheduled | Check `flint list -n <ns>`; confirm the deploy succeeded and pods exist. |
| 9 | Deploy never becomes ready (`--wait` times out) | Image pull / weight download slow, or no GPU for a GPU runtime | Check `flint logs <model>`; ensure GPU nodes for vllm/tgi; raise `--wait-timeout`. |
| 10 | `flint route` split not taking effect | Requests not matching the route hostname | Send requests with the route's `Host` header (default `<model>.local`, or `--host`). |

## Runtime behavior notes

- **vLLM** (`--hf-repo`): weights download into the mounted PVC (`HF_HOME=/weights`)
  and persist across pod restarts. The PVC defaults to `ReadWriteOnce`; use
  `--weights-access-mode ReadWriteMany` for multi-replica on a StorageClass
  that supports it.
- **Ollama**: the model is pulled into an `emptyDir` per pod, so it is
  re-downloaded whenever a pod is recreated. Fine for small models; expect a
  cold-start delay after restarts.
- **TGI**: weights download into an ephemeral `/data` per pod (re-downloaded on
  restart), and TGI is GPU-oriented (CUDA image).
- **HPA**: not created by default (CPU-based autoscaling is a poor fit for
  GPU-bound inference). Opt in with `flint deploy ... --hpa`.

## Getting more detail

- `--debug` (or `FLINT_DEBUG=1`): print full Python tracebacks on error.
- `--verbose` / `-v`: enable INFO-level logging (shows kubectl-equivalent actions).
- `flint status <model>`: replica readiness, endpoint, and current traffic split.
- `flint logs <model> --tail 100`: recent runtime logs.
