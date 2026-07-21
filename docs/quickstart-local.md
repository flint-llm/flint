# Quickstart — local (3 minutes)

Serve a model on your own machine behind an OpenAI-compatible endpoint. No
Kubernetes, no GPU, no cloud account.

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com) installed and on your `PATH`:

    === "macOS"

        ```bash
        brew install ollama
        ```

    === "Linux"

        ```bash
        curl -fsSL https://ollama.com/install.sh | sh
        ```

`flint serve` is macOS and Linux only. (`flint version` and `flint init` work
everywhere.)

## 1. Install Flint

```bash
pip install flint-llm
flint version
```

```text
flint 0.1.0
```

## 2. Serve a model

```bash
flint serve tinyllama
```

Flint starts the Ollama daemon, pulls `tinyllama` if it isn't already on disk,
waits for it to be healthy, and prints:

```text
Endpoint:  http://localhost:11434/v1
Example:   curl -N http://localhost:11434/v1/chat/completions \
               -H "Content-Type: application/json" \
               -d '{"model": "tinyllama", "stream": true, "messages": [{"role": "user", "content": "hi"}]}'

Press Ctrl+C to stop.
```

The first run downloads the model (~640 MB for `tinyllama`), so it takes longer
than later runs. Use `--port` if 11434 is taken:

```bash
flint serve tinyllama --port 12000
```

Any model in the [Ollama library](https://ollama.com/library) works —
`llama3.2`, `qwen2.5`, `phi3`, and so on.

## 3. Send a request

Leave `flint serve` running and open a second terminal.

=== "curl"

    ```bash
    curl -N http://localhost:11434/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{"model":"tinyllama","stream":true,
           "messages":[{"role":"user","content":"Say hi in one word."}]}'
    ```

=== "OpenAI Python SDK"

    ```python
    from openai import OpenAI

    client = OpenAI(base_url="http://localhost:11434/v1", api_key="unused")

    stream = client.chat.completions.create(
        model="tinyllama",
        messages=[{"role": "user", "content": "Say hi in one word."}],
        stream=True,
    )
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    ```

The endpoint is OpenAI-compatible, so any client that accepts a `base_url`
works unchanged. The server does not check `api_key` — send any non-empty
string.

## 4. Stop

Press ++ctrl+c++ in the terminal running `flint serve`. Flint signals the Ollama
process group and force-kills after 5 seconds, so nothing is left behind.

## Next

- Run the same thing as a scripted 60-second demo:
  [`demo/local-quickstart.sh`](https://github.com/flint-llm/flint/blob/main/demo/local-quickstart.sh)
- Move to a cluster: [Kubernetes quickstart](quickstart-cluster.md)

!!! note "Local mode vs. the `ollama` runtime"

    `flint serve` runs Ollama as a local subprocess on your machine. That is a
    different path from `flint deploy --runtime ollama`, which runs the Ollama
    container in your cluster. See [Runtimes](runtimes.md).
