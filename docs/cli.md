# CLI reference

Every command and option, generated from the installed CLI — so this page and
`flint --help` cannot drift apart.

Global flags (`--debug`, `--verbose`) go before the subcommand:

```bash
flint --verbose deploy mistral --gpu 1 --wait
```

::: mkdocs-click
    :module: flint.cli.main
    :command: cli
    :prog_name: flint
    :depth: 1
    :style: table
