"""Domain vocabulary — ModelRef, ResourceSpec, RenderContext, TrafficSplit.

These types are the shared language all flint/core modules speak. S2 and S3
import from here. Change field names carefully — they map to Jinja2 template
variables and Kubernetes resource specs.

Schema version is bumped (SCHEMA_VERSION constant) whenever RenderContext
fields are added or renamed, so callers can detect incompatible contexts.
"""

from __future__ import annotations

import base64
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from flint.core.errors import WeightsValidationError

SCHEMA_VERSION: int = 3


class WeightsStrategy(StrEnum):
    """How model weights reach the runtime container."""

    HF_HUB = "hf_hub"
    PRELOADED = "preloaded"


class ModelRef(BaseModel):
    """Identifies a model to deploy or serve."""

    name: str
    version: str = "latest"
    image: str | None = None
    hf_repo: str | None = None
    weights_strategy: WeightsStrategy = WeightsStrategy.HF_HUB

    @field_validator("name", "version")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_model_name(v)


class ResourceSpec(BaseModel):
    """CPU, memory, and GPU allocation for a runtime pod."""

    cpu_request: str = "500m"
    cpu_limit: str = "2000m"
    memory_request: str = "1Gi"
    memory_limit: str = "4Gi"
    gpu_count: int = Field(default=0, ge=0)
    gpu_type: str = "nvidia.com/gpu"


class ReadinessProbe(BaseModel):
    """HTTP readiness probe configuration."""

    port: int = Field(default=8080, gt=0, lt=65536)
    path: str = "/health"
    initial_delay_seconds: int = Field(default=30, ge=0)
    period_seconds: int = Field(default=10, gt=0)
    failure_threshold: int = Field(default=3, gt=0)


class RenderContext(BaseModel):
    """Everything a Jinja2 template needs to render a complete deployment.

    Passed as a flat dict to Jinja2; nested objects are also accessible
    via dotted attribute syntax in templates.
    """

    schema_version: int = SCHEMA_VERSION
    model_name: str
    model_version: str
    namespace: str = "flint"
    runtime: str
    image: str
    replicas: int = Field(default=1, ge=1)
    resources: ResourceSpec = Field(default_factory=ResourceSpec)
    readiness_probe: ReadinessProbe = Field(default_factory=ReadinessProbe)
    hf_repo: str | None = None
    hf_token_secret: str | None = None
    service_port: int = Field(default=8080, gt=0, lt=65536)
    weights_volume_size: str = "50Gi"
    # RWO works with every default StorageClass (kind local-path, EBS, GCE PD)
    # for the single-replica default. Use ReadWriteMany for multi-replica on a
    # cluster whose StorageClass supports it.
    weights_access_mode: str = "ReadWriteOnce"
    labels: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class TrafficWeight(BaseModel):
    """A single version's share of traffic."""

    version: str
    weight: int = Field(ge=0, le=100)


class TrafficSplit(BaseModel):
    """Validated traffic split across model versions. Weights must sum to 100."""

    model_name: str
    weights: list[TrafficWeight]

    @field_validator("weights")
    @classmethod
    def _weights_sum_to_100(cls, v: list[TrafficWeight]) -> list[TrafficWeight]:
        total = sum(w.weight for w in v)
        if total != 100:
            raise ValueError(f"Traffic weights sum to {total}, expected 100")
        return v


class DeployResult(BaseModel):
    """Outcome of a deploy: what was applied and where to reach it."""

    model_name: str
    model_version: str
    namespace: str
    applied_manifests: list[Path]
    endpoint: str
    ready: bool = False


class DeploymentStatus(BaseModel):
    """Observed state of a flint-managed deployment."""

    name: str
    model_name: str
    model_version: str
    namespace: str
    replicas: int
    ready_replicas: int
    endpoint: str


# ── Utility functions ported from monolith ────────────────────────────────────


def normalize_model_name(name: str) -> str:
    """Normalise a model name or version tag to a lowercase string.

    Ported from monolith `_validate_and_prep_model_tag` (lines 324-329).
    """
    return str(name).lower()


def validate_traffic_weights(weights: dict[str, int]) -> None:
    """Raise WeightsValidationError if weights do not sum to exactly 100.

    Ported from monolith `_validate_and_prep_model_split_tag_and_weight_dict`
    (lines 332-340).
    """
    total = sum(int(w) for w in weights.values())
    if total != 100:
        raise WeightsValidationError(
            f"Traffic weights sum to {total} (expected 100): {weights}"
        )


def is_base64_encoded(data: str | bytes) -> bool:
    """Return True if *data* appears to be valid base64-encoded content.

    Ported from monolith `_is_base64_encoded` (lines 562-574).
    """
    raw: bytes = data.encode("utf-8") if isinstance(data, str) else data
    try:
        return base64.b64encode(base64.b64decode(raw)) == raw
    except Exception:
        return False


def decode_base64(data: str | bytes) -> str:
    """Decode a base64-encoded value to plain text.

    Ported from monolith `_decode_base64` (lines 577-578).
    """
    raw: bytes = data.encode("utf-8") if isinstance(data, str) else data
    return base64.b64decode(raw).decode("utf-8")
