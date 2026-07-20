# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-dev] - Unreleased

### Changed
- Renamed the PyPI distribution to `flint-llm` (`pip install flint-llm`). The
  import package and the `flint` CLI command are unchanged.

### Added
- Project scaffold, CI (ruff/mypy/pytest), and typed `flint/core` modules
  salvaged and decomposed from the legacy Dataspine monolith (S0–S1).
- `flint serve` — local OpenAI-compatible serving via Ollama (S2).
- `flint deploy` — deploy models to Kubernetes via server-side apply, with
  `--dry-run`, readiness polling, and idempotent re-deploys (S3).
- Multi-runtime support: vLLM, Ollama, and TGI behind a `RuntimeAdapter`
  protocol, selectable with `--runtime` (S4).
- `flint route` — canary/cutover traffic splits between versions via the
  Gateway API HTTPRoute (S5).
- Operational commands: `flint list`, `flint status`, `flint delete`, and
  `flint logs`, plus consistent error handling and `--verbose`/`--debug` (S6).
