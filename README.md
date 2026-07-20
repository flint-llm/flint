# Flint

Deploy LLMs to Kubernetes.

> **v0.1.0 — early (alpha) release.** Interfaces may still change; try it on a
> non-production cluster first. The GPU serving paths (vLLM, TGI) are best
> validated on your own hardware.

Flint is an open-source CLI that deploys large language models to your own Kubernetes cluster and routes traffic between versions. It uses your existing kubeconfig; there is no Flint server to operate.

## Install

```bash
pip install flint-llm    # the distribution is flint-llm; the CLI command is `flint`
```

## Status

Alpha — v0.1.0. See [CHANGELOG.md](CHANGELOG.md) for what's included and
[docs/troubleshooting.md](docs/troubleshooting.md) for common errors.

## License

Apache 2.0. See [LICENSE](LICENSE).
