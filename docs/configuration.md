# Configuration

Flint is configured three ways, in this order of precedence:

```
CLI flag  >  flint.toml  >  built-in default
```

Everything works without any configuration at all — `flint.toml` only exists so
a project can stop repeating the same flags.

## flint.toml

Scaffold one in the current directory:

```bash
flint init          # --force to overwrite an existing file
```

```toml
[project]
name = "my-project"

[defaults]
runtime = "ollama"
model = ""

[templates]
# dir = "./flint-templates"   # uncomment to override built-in templates
```

| Key | Effect | Built-in default |
|-----|--------|------------------|
| `project.name` | Informational; identifies the project. | directory name |
| `defaults.runtime` | Runtime when `--runtime` is omitted. | `vllm` |
| `defaults.model` | Lets you run `flint deploy` with no model argument. | none |
| `templates.dir` | Directory of Jinja2 manifest templates to use instead of the built-ins. | packaged templates |

Every key is optional, and a blank value counts as unset. Flint reads
`./flint.toml` by default; point elsewhere with `flint deploy --config
path/to/flint.toml`.

With `defaults.model` set, this works:

```bash
flint deploy            # deploys [defaults].model with [defaults].runtime
```

An invalid file is an error, not a warning — malformed TOML, a non-table
`[project]`/`[defaults]`/`[templates]`, or a wrong-typed value all stop the
command rather than silently falling back.

## Global flags

Available on every command:

| Flag | Effect |
|------|--------|
| `--debug` | Print full Python tracebacks on error (also `FLINT_DEBUG=1`). |
| `-v, --verbose` | INFO-level logging: what Flint is applying and waiting on. |

They go before the subcommand: `flint --verbose deploy mistral`.

## Cluster selection

Flint has no cluster configuration of its own. It uses the current kubeconfig
context, exactly like `kubectl`:

```bash
kubectl config current-context     # the cluster Flint will act on
kubectl config use-context prod    # switch
KUBECONFIG=/path/to/kubeconfig flint list
```

Namespaces default to `flint` and are created on demand by `flint deploy`. Pass
`-n/--namespace` to any cluster command to work elsewhere.

## Custom templates

Manifests are Jinja2 templates shipped inside the package, one directory per
runtime (`templates/runtimes/<runtime>/`). To customise them — node selectors,
tolerations, sidecars, labels your platform requires — copy the built-ins,
edit, and point Flint at your copy:

```bash
flint deploy mistral --templates-dir ./flint-templates
```

Or set `templates.dir` in `flint.toml`. Your directory must keep the same
per-runtime layout and filenames. Preview the result before applying:

```bash
flint deploy mistral --templates-dir ./flint-templates --dry-run
```

!!! note

    Custom templates are unversioned: they are yours to keep in step with Flint
    releases. Prefer flags where a flag exists.

## Labels Flint sets

Every object Flint creates carries:

- `flint.dev/managed: "true"`
- `flint.dev/model: <model>`
- `flint.dev/version: <version>` (workloads)
- `flint.dev/runtime: <runtime>` (workloads)

`flint list`, `flint status`, and `flint delete` select on these, which is also
how you can find Flint's objects with plain `kubectl`:

```bash
kubectl -n flint get all -l flint.dev/managed=true
```
