"""Pod log retrieval via the Python kubernetes client.

Finds the pod backing a flint-managed model (by the flint.dev/model label) and
yields its logs, with optional follow / since / tail. No kubectl dependency.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterator
from typing import Any

from flint.core.errors import K8sError, ModelNotFoundError
from flint.core.k8s_apply import _load_k8s_config

logger = logging.getLogger(__name__)


def find_model_pod(
    model_name: str, namespace: str, version: str | None = None
) -> str:
    """Return a pod name for *model_name* (preferring a Running pod).

    Selects on the ``flint.dev/model`` label (optionally narrowed to
    *version*).

    Raises:
        ModelNotFoundError: If no matching pod exists.
        K8sError: If the pod list call fails.
    """
    _load_k8s_config()
    import kubernetes.client as k8s_client

    selector = f"flint.dev/model={model_name}"
    if version:
        selector += f",flint.dev/version={version}"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = k8s_client.CoreV1Api()
        try:
            pods: list[Any] = v1.list_namespaced_pod(
                namespace, label_selector=selector
            ).items
        except Exception as exc:
            raise K8sError(
                f"Failed to list pods for {model_name!r} in {namespace}: {exc}"
            ) from exc

    if not pods:
        raise ModelNotFoundError(
            f"No pods found for model {model_name!r} in namespace {namespace!r}."
        )
    running = [p for p in pods if str(getattr(p.status, "phase", "")) == "Running"]
    chosen = running[0] if running else pods[0]
    return str(chosen.metadata.name)


def iter_pod_logs(
    model_name: str,
    namespace: str,
    *,
    version: str | None = None,
    container: str | None = None,
    since_seconds: int | None = None,
    tail_lines: int | None = None,
    follow: bool = False,
) -> Iterator[str]:
    """Yield log text for *model_name*'s pod.

    Without *follow*, yields the current logs once. With *follow*, streams new
    output until the caller stops iterating. Text is yielded in chunks, not
    necessarily whole lines.

    Raises:
        ModelNotFoundError: If no pod is found.
        K8sError: If the log request fails.
    """
    pod_name = find_model_pod(model_name, namespace, version)
    _load_k8s_config()
    import kubernetes.client as k8s_client

    kwargs: dict[str, Any] = {"name": pod_name, "namespace": namespace}
    if container is not None:
        kwargs["container"] = container
    if since_seconds is not None:
        kwargs["since_seconds"] = since_seconds
    if tail_lines is not None:
        kwargs["tail_lines"] = tail_lines

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = k8s_client.CoreV1Api()
        if follow:
            try:
                resp = v1.read_namespaced_pod_log(
                    follow=True, _preload_content=False, **kwargs
                )
            except Exception as exc:
                raise K8sError(
                    f"Failed to stream logs for {pod_name!r}: {exc}"
                ) from exc
            try:
                for chunk in resp.stream():
                    yield chunk.decode("utf-8", errors="replace")
            finally:
                resp.release_conn()
        else:
            try:
                text = v1.read_namespaced_pod_log(**kwargs)
            except Exception as exc:
                raise K8sError(
                    f"Failed to read logs for {pod_name!r}: {exc}"
                ) from exc
            if text:
                yield str(text)
