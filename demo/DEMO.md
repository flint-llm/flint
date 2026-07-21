# Flint demo (60 seconds)

A short, reproducible demo for the README / launch. Two flows: a **local** one
that runs on any laptop, and a **cluster** one you run against your own cluster.

## Local demo (runnable anywhere)

Prereqs: `pip install flint-llm` and [Ollama](https://ollama.com) installed.

```bash
bash demo/local-quickstart.sh
```

It runs, in ~60s: `flint version` → `flint serve tinyllama` (an
OpenAI-compatible endpoint) → a streamed `/v1/chat/completions` request →
clean shutdown.

### Record it

```bash
# Record a terminal cast
asciinema rec -c "bash demo/local-quickstart.sh" flint-local.cast

# (optional) Convert to a GIF/SVG for the README
agg flint-local.cast flint-local.gif           # https://github.com/asciinema/agg
# or: svg-term --in flint-local.cast --out flint-local.svg
```

Then embed in the README, e.g. `![Flint demo](demo/flint-local.gif)`.

## Cluster demo (run against your own cluster)

Needs a Kubernetes cluster in your kubeconfig (GPU nodes for vLLM). The exact
sequence to type/record:

```bash
flint deploy demo --runtime vllm \
  --hf-repo facebook/opt-125m --gpu 1 --wait
flint status demo                     # readiness + endpoint
flint logs demo --tail 20             # runtime logs
flint route demo --to v1              # baseline traffic
flint delete demo                     # tear down
```

Record the same way: `asciinema rec` and run the commands live.
