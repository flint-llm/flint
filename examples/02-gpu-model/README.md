# 02 — A 7B model on GPU with vLLM

Deploy Mistral-7B-Instruct to a GPU cluster with vLLM: persistent weights on a
PVC, an optional HuggingFace token for gated repos, and a real completion at the
end.

- **Time:** ~20 minutes, mostly downloading ~15 GB of weights
- **Needs:** a cluster with GPU nodes advertising `nvidia.com/gpu` (the NVIDIA
  device plugin installed), `kubectl`, `flint`

> **No GPUs?** Run [01-cpu-model](../01-cpu-model/) instead. The script checks
> GPU capacity up front and stops with that suggestion rather than leaving a Pod
> Pending forever.

## Run it

```bash
pip install flint-llm
./run.sh
```

Gated repo (Llama, some Mistral builds)? Provide a token — the script puts it in
a Secret and passes `--hf-token-secret`:

```bash
HF_TOKEN=hf_xxx ./run.sh
```

Everything is overridable:

```bash
MODEL=llama3 HF_REPO=meta-llama/Llama-3.1-8B-Instruct GPUS=2 HF_TOKEN=hf_xxx ./run.sh
```

> **Note:** `MODEL` is the name clients ask for and it becomes a Kubernetes
> resource name, so it must be a DNS-1123 label (lowercase, digits, `-`).
> `HF_REPO` is what vLLM actually loads. They are deliberately independent.

## What it does

1. **Checks GPU capacity** by summing `nvidia.com/gpu` across nodes, and stops
   with a useful message if there isn't enough.

2. **Creates a Secret** (only when `HF_TOKEN` is set) with the token under the
   key `token` — the key Flint expects.

3. **Deploys** with vLLM:

    ```bash
    flint deploy mistral --runtime vllm \
      --hf-repo mistralai/Mistral-7B-Instruct-v0.3 \
      --gpu 1 --namespace flint-example-02 \
      --weights-volume-size 50Gi \
      --memory-request 16Gi --memory-limit 32Gi \
      --wait --wait-timeout 1800
    ```

    That creates a PVC, a Deployment and a Service. `--wait-timeout 1800` is
    deliberate: the first start pulls a multi-GB image *and* downloads weights.

    > **Raise the memory limit whenever you raise the request.** The defaults
    > are `1Gi` request / `4Gi` limit. Passing `--memory-request 16Gi` on its own
    > leaves the limit at `4Gi`, and Kubernetes rejects any Pod whose request
    > exceeds its limit — Flint does not catch this for you in v0.1.

4. **Calls it** via port-forward — `/v1/models`, then `/v1/chat/completions`.

## Weights persist; pods don't

vLLM mounts the PVC at `/weights` and sets `HF_HOME` to it, so a restarted pod
reuses the download. Two consequences:

- `flint delete` removes the PVC by default — the next deploy re-downloads
  everything. Use `--keep-weights` when you intend to come back:

    ```bash
    flint delete mistral -n flint-example-02 --keep-weights --yes
    ```

- The PVC defaults to `ReadWriteOnce`, which one node can mount. For several
  replicas sharing one volume you need `ReadWriteMany` on a StorageClass that
  supports it:

    ```bash
    flint deploy mistral --runtime vllm --hf-repo ... --gpu 1 \
      --replicas 3 --weights-access-mode ReadWriteMany --wait
    ```

## If the rollout does not become ready

```bash
flint logs mistral -n flint-example-02 --follow    # what vLLM is doing
kubectl -n flint-example-02 describe pod -l flint.dev/model=mistral
kubectl -n flint-example-02 get pvc                # Pending => no StorageClass?
```

Common causes: no GPU node matches (Pending), the image pull is still running,
the repo is gated and the token is missing or wrong (401 in the logs), or the
model does not fit in GPU memory (CUDA OOM — try a smaller model or more GPUs).
More in [Troubleshooting](https://flint-llm.github.io/flint/troubleshooting/).

## Cleanup

```bash
./run.sh cleanup      # deletes the model, the PVC, and the namespace
```

## Next

- [03-canary-rollout](../03-canary-rollout/) — two versions, weighted traffic
