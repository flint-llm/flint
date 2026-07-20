"""Tests for flint.core.deploy (orchestration; k8s calls mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from flint.core.deploy import (
    _order_manifests,
    build_render_context,
    delete_model,
    deploy_model,
    render_manifests,
)
from flint.core.errors import TemplateRenderError, UnsupportedRuntimeError
from flint.core.models import ModelRef, RenderContext, ResourceSpec


def _rendered(tmp: Path, model: str = "m", version: str = "v1") -> list[Path]:
    """Manifests in the order render_deployment_templates produces them."""
    return [
        tmp / f"{model}-{version}-deployment.yaml",
        tmp / f"{model}-{version}-service.yaml",
        tmp / f"{model}-{version}-hpa.yaml",
        tmp / f"{model}-{version}-pvc.yaml",
    ]


# -- build_render_context -----------------------------------------------------


def test_build_context_uses_adapter_defaults() -> None:
    model = ModelRef(name="mistral", version="v1")
    ctx = build_render_context(model, "vllm", "flint")
    assert "vllm/vllm-openai" in ctx.image  # adapter default image
    assert ctx.service_port == 8080  # adapter default port
    assert ctx.readiness_probe.path == "/health"  # adapter default probe
    assert ctx.model_name == "mistral"
    assert ctx.namespace == "flint"
    assert ctx.runtime == "vllm"


def test_build_context_prefers_explicit_image() -> None:
    model = ModelRef(name="mistral", version="v1", image="custom/img:1")
    ctx = build_render_context(model, "vllm", "flint")
    assert ctx.image == "custom/img:1"


def test_build_context_unsupported_runtime_raises() -> None:
    with pytest.raises(UnsupportedRuntimeError, match="Unsupported runtime"):
        build_render_context(ModelRef(name="m", version="v1"), "bogus", "flint")


def test_build_context_threads_hf_repo_and_overrides() -> None:
    model = ModelRef(name="mistral", version="v1", hf_repo="org/mistral")
    ctx = build_render_context(
        model,
        "vllm",
        "prod",
        replicas=3,
        resources=ResourceSpec(gpu_count=2),
        hf_token_secret="hf-secret",
        service_port=9000,
        weights_volume_size="100Gi",
    )
    assert ctx.hf_repo == "org/mistral"
    assert ctx.replicas == 3
    assert ctx.resources.gpu_count == 2
    assert ctx.hf_token_secret == "hf-secret"
    assert ctx.service_port == 9000
    assert ctx.weights_volume_size == "100Gi"


# -- deploy_model: ordering + conditional PVC ---------------------------------


def _run_deploy(tmp: Path, *, hf_repo: str | None, wait: bool = False):  # type: ignore[no-untyped-def]
    ctx = RenderContext(
        model_name="m",
        model_version="v1",
        runtime="vllm",
        image="img",
        namespace="flint",
        hf_repo=hf_repo,
    )
    with (
        patch("flint.core.deploy.ensure_namespace") as mock_ns,
        patch(
            "flint.core.deploy.render_deployment_templates",
            return_value=_rendered(tmp),
        ),
        patch("flint.core.deploy.kube_apply") as mock_apply,
        patch("flint.core.deploy.wait_for_rollout") as mock_wait,
    ):
        result = deploy_model(ctx, output_dir=tmp, wait=wait)
    applied = [call.args[0].name for call in mock_apply.call_args_list]
    return result, applied, mock_ns, mock_wait


def test_deploy_ensures_namespace(tmp_path: Path) -> None:
    _result, _applied, mock_ns, _wait = _run_deploy(tmp_path, hf_repo=None)
    mock_ns.assert_called_once_with("flint")


def test_deploy_apply_order_without_pvc(tmp_path: Path) -> None:
    # No hf_repo -> PVC is rendered but not applied.
    _result, applied, _ns, _wait = _run_deploy(tmp_path, hf_repo=None)
    assert applied == [
        "m-v1-deployment.yaml",
        "m-v1-service.yaml",
        "m-v1-hpa.yaml",
    ]


def test_deploy_apply_order_with_pvc(tmp_path: Path) -> None:
    # hf_repo set -> PVC applied first, before the Deployment that mounts it.
    _result, applied, _ns, _wait = _run_deploy(tmp_path, hf_repo="org/m")
    assert applied == [
        "m-v1-pvc.yaml",
        "m-v1-deployment.yaml",
        "m-v1-service.yaml",
        "m-v1-hpa.yaml",
    ]


def test_render_manifests_excludes_hpa_when_disabled(tmp_path: Path) -> None:
    ctx = RenderContext(
        model_name="m", model_version="v1", runtime="vllm", image="img",
        namespace="flint", hf_repo="org/m",
    )
    with patch(
        "flint.core.deploy.render_deployment_templates",
        return_value=_rendered(tmp_path),
    ):
        names = [p.name for p in render_manifests(ctx, output_dir=tmp_path, include_hpa=False)]
    assert "m-v1-hpa.yaml" not in names
    assert "m-v1-deployment.yaml" in names


# -- deploy_model: wait + result ----------------------------------------------


def test_deploy_no_wait_skips_rollout(tmp_path: Path) -> None:
    result, _applied, _ns, mock_wait = _run_deploy(tmp_path, hf_repo=None, wait=False)
    mock_wait.assert_not_called()
    assert result.ready is False


def test_deploy_wait_calls_rollout_and_sets_ready(tmp_path: Path) -> None:
    result, _applied, _ns, mock_wait = _run_deploy(tmp_path, hf_repo=None, wait=True)
    mock_wait.assert_called_once_with("m-v1", "flint", timeout_s=600, on_progress=None)
    assert result.ready is True


def test_deploy_result_shape(tmp_path: Path) -> None:
    result, applied, _ns, _wait = _run_deploy(tmp_path, hf_repo=None)
    assert result.model_name == "m"
    assert result.model_version == "v1"
    assert result.namespace == "flint"
    assert result.endpoint == "http://m-v1.flint.svc.cluster.local/v1"
    assert [p.name for p in result.applied_manifests] == applied


# -- _order_manifests robustness ----------------------------------------------


def test_deploy_empty_render_raises(tmp_path: Path) -> None:
    # A runtime with no templates renders nothing; deploy must fail loudly
    # rather than "succeed" having applied nothing.
    ctx = RenderContext(
        model_name="m", model_version="v1", runtime="vllm", image="img"
    )
    with (
        patch("flint.core.deploy.ensure_namespace"),
        patch("flint.core.deploy.render_deployment_templates", return_value=[]),
        patch("flint.core.deploy.kube_apply") as mock_apply,
    ):
        with pytest.raises(TemplateRenderError, match="No manifests"):
            deploy_model(ctx, output_dir=tmp_path)
    mock_apply.assert_not_called()


def test_render_manifests_orders_without_cluster_calls(tmp_path: Path) -> None:
    ctx = RenderContext(
        model_name="m",
        model_version="v1",
        runtime="vllm",
        image="img",
        namespace="flint",
        hf_repo="org/m",  # PVC included
    )
    with patch(
        "flint.core.deploy.render_deployment_templates",
        return_value=_rendered(tmp_path),
    ):
        ordered = render_manifests(ctx, output_dir=tmp_path)
    assert [p.name for p in ordered] == [
        "m-v1-pvc.yaml",
        "m-v1-deployment.yaml",
        "m-v1-service.yaml",
        "m-v1-hpa.yaml",
    ]


def test_render_manifests_empty_raises(tmp_path: Path) -> None:
    ctx = RenderContext(
        model_name="m", model_version="v1", runtime="vllm", image="img"
    )
    with patch("flint.core.deploy.render_deployment_templates", return_value=[]):
        with pytest.raises(TemplateRenderError, match="No manifests"):
            render_manifests(ctx, output_dir=tmp_path)


def test_delete_model_all_versions_deletes_everything() -> None:
    with patch("flint.core.deploy.delete_by_label", return_value=[]) as m:
        delete_model("demo", "flint")
    kinds = [c.args[1] for c in m.call_args_list]
    assert kinds == [
        "Deployment",
        "Service",
        "HorizontalPodAutoscaler",
        "PersistentVolumeClaim",
        "HTTPRoute",
    ]
    # versioned selector is the model label only (no version)
    assert m.call_args_list[0].args[3] == "flint.dev/model=demo"
    # the HTTPRoute delete tolerates a missing Gateway API CRD
    assert m.call_args_list[-1].kwargs.get("ignore_missing_crd") is True


def test_delete_model_version_scopes_and_keeps_shared() -> None:
    with patch("flint.core.deploy.delete_by_label", return_value=[]) as m:
        delete_model("demo", "flint", version="v1")
    kinds = [c.args[1] for c in m.call_args_list]
    assert kinds == ["Deployment", "Service", "HorizontalPodAutoscaler"]
    assert m.call_args_list[0].args[3] == "flint.dev/model=demo,flint.dev/version=v1"


def test_delete_model_keep_weights_skips_pvc() -> None:
    with patch("flint.core.deploy.delete_by_label", return_value=[]) as m:
        delete_model("demo", "flint", keep_weights=True)
    kinds = [c.args[1] for c in m.call_args_list]
    assert "PersistentVolumeClaim" not in kinds
    assert "HTTPRoute" in kinds


def test_delete_model_returns_deleted_names() -> None:
    with patch(
        "flint.core.deploy.delete_by_label",
        side_effect=[["Deployment/demo-v1"], ["Service/demo-v1"], [], [], []],
    ):
        deleted = delete_model("demo", "flint")
    assert deleted == ["Deployment/demo-v1", "Service/demo-v1"]


def test_order_is_suffix_based_not_substring(tmp_path: Path) -> None:
    # A model name containing a resource keyword must not misclassify.
    paths = [
        tmp_path / "pvc-bot-v1-deployment.yaml",
        tmp_path / "pvc-bot-v1-pvc.yaml",
        tmp_path / "pvc-bot-v1-service.yaml",
    ]
    ordered = _order_manifests(paths, include_pvc=True)
    assert [p.name for p in ordered] == [
        "pvc-bot-v1-pvc.yaml",
        "pvc-bot-v1-deployment.yaml",
        "pvc-bot-v1-service.yaml",
    ]
