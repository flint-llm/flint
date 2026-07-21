# Traffic routing

`flint route` shifts traffic between deployed versions of a model — canary a
new version, then cut over — without clients changing the URL they call.

Flint manages one [Gateway API](https://gateway-api.sigs.k8s.io) `HTTPRoute`
per model. The route matches a hostname and splits weighted `backendRefs`
across the per-version Services that `flint deploy` created.

```
                    ┌──────────── HTTPRoute (managed by flint) ────────────┐
client ──▶ Gateway ─┤  host: mistral.local                                 │
                    │    90% ──▶ Service mistral-v1 ──▶ pods (vLLM)        │
                    │    10% ──▶ Service mistral-v2 ──▶ pods (vLLM)        │
                    └──────────────────────────────────────────────────────┘
```

## Prerequisites

Flint does **not** install a Gateway — your cluster owns it. You need:

1. **A Gateway API implementation.** For example
   [Envoy Gateway](https://gateway.envoyproxy.io/docs/install/):

    ```bash
    helm install eg oci://docker.io/envoyproxy/gateway-helm \
      -n envoy-gateway-system --create-namespace
    ```

    Or just the CRDs, if your ingress already implements Gateway API:

    ```bash
    kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/latest/download/standard-install.yaml
    ```

2. **A Gateway resource** Flint can attach routes to. By default Flint looks
   for one named `flint-gateway` in the model's namespace (override with
   `--gateway` / `--gateway-namespace`):

    ```yaml
    apiVersion: gateway.networking.k8s.io/v1
    kind: Gateway
    metadata:
      name: flint-gateway
      namespace: flint
    spec:
      gatewayClassName: eg          # your implementation's GatewayClass
      listeners:
        - name: http
          protocol: HTTP
          port: 80
          allowedRoutes:
            namespaces:
              from: Same
    ```

If the CRDs are missing, `flint route` fails up front with install pointers
rather than applying a partial change.

## Deploy two versions

Versions are just deploy-time tags; each gets its own Deployment and Service.

```bash
flint deploy mistral --version v1 --runtime vllm \
  --hf-repo mistralai/Mistral-7B-Instruct-v0.2 --gpu 1 --wait

flint deploy mistral --version v2 --runtime vllm \
  --hf-repo mistralai/Mistral-7B-Instruct-v0.3 --gpu 1 --wait
```

## Establish a baseline

Every split needs a baseline before you can canary against it:

```bash
flint route mistral --to v1
```

```text
Routed mistral (host mistral.local):
  v1: 100%
```

## Canary

```bash
flint route mistral --canary 10 v2      # 90% v1 / 10% v2
```

Watch it, then widen or cut over:

```bash
flint logs mistral --version v2 --follow
flint route mistral --canary 50 v2      # 50/50
flint route mistral --to v2             # 100% v2 — done
```

`--canary` is always computed against the *current* route, so the remaining
weight stays on the existing baseline. It requires exactly one baseline: if the
split already spans several versions, consolidate first with `--to`.

## Inspect

```bash
flint route mistral --show
flint status mistral         # readiness and the split together
```

## Sending traffic

The route matches a hostname — `<model>.local` by default, or `--host` for a
real DNS name you own:

```bash
flint route mistral --to v1 --host mistral.example.com
```

Requests must carry that `Host` header, or the Gateway will not match them.
Against a local Gateway with a port-forward:

```bash
kubectl -n envoy-gateway-system port-forward svc/<gateway-service> 8080:80

curl http://localhost:8080/v1/chat/completions \
  -H "Host: mistral.local" \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral","messages":[{"role":"user","content":"Hello!"}]}'
```

!!! warning "A split that seems to do nothing"

    Nearly always a hostname mismatch: the request did not carry the `Host`
    the route matches. Check with `flint route <model> --show` and
    `kubectl -n <ns> get httproute <model> -o yaml`.

## Cleanup

`flint delete <model>` removes the model's HTTPRoute along with its workloads.
The Gateway itself is yours and is left alone.

## Limits in v0.1

- **Weighted splits only.** Header- and path-based matching, mirroring/shadow
  traffic, and automatic rollback on error rates are not in 0.1.
- **One route per model**, named after the model, in the model's namespace.
- **Backends are addressed on port 80**, the port `flint deploy` gives each
  Service.
