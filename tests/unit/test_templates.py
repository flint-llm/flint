"""Tests for flint.core.templates."""

from __future__ import annotations

from pathlib import Path

import pytest

from flint.core.errors import TemplateRenderError
from flint.core.models import RenderContext, ResourceSpec
from flint.core.templates import (
    _flatten_context,
    get_templates_dir,
    render_deployment_templates,
    render_template,
    render_template_to_file,
    resolve_templates_path,
)

# -- get_templates_dir --------------------------------------------------------


def test_get_templates_dir_exists() -> None:
    d = get_templates_dir()
    assert d.is_dir()


def test_get_templates_dir_contains_vllm() -> None:
    d = get_templates_dir()
    assert (d / "vllm").is_dir()


# -- resolve_templates_path ---------------------------------------------------


def test_resolve_none_returns_builtin() -> None:
    d = resolve_templates_path(None)
    assert d.is_dir()
    assert d == get_templates_dir()


def test_resolve_valid_path(tmp_path: Path) -> None:
    assert resolve_templates_path(tmp_path) == tmp_path


def test_resolve_missing_path_raises() -> None:
    with pytest.raises(TemplateRenderError, match="not found"):
        resolve_templates_path("/nonexistent/path/99999")


# -- _flatten_context ---------------------------------------------------------


def test_flatten_context_shortcuts() -> None:
    ctx = RenderContext(
        model_name="mistral",
        model_version="v1",
        runtime="vllm",
        image="vllm/vllm-openai:latest",
        resources=ResourceSpec(gpu_count=2, gpu_type="amd.com/gpu"),
    )
    flat = _flatten_context(ctx)
    assert flat["gpu_count"] == 2
    assert flat["gpu_type"] == "amd.com/gpu"
    assert flat["model_name"] == "mistral"
    assert flat["readiness_port"] == 8080
    assert flat["readiness_path"] == "/health"


def test_flatten_context_contains_all_model_fields() -> None:
    ctx = RenderContext(
        model_name="m", model_version="v1", runtime="vllm", image="img"
    )
    flat = _flatten_context(ctx)
    assert "model_name" in flat
    assert "namespace" in flat
    assert "replicas" in flat


# -- render_template ----------------------------------------------------------


def _ctx(**kwargs: object) -> RenderContext:
    base = {"model_name": "mistral", "model_version": "v1", "runtime": "vllm", "image": "img"}
    base.update(kwargs)  # type: ignore[arg-type]
    return RenderContext(**base)  # type: ignore[arg-type]


def test_render_deployment_template_produces_yaml() -> None:
    ctx = _ctx()
    rendered = render_template("vllm/deployment.yaml.j2", ctx)
    assert "kind: Deployment" in rendered
    assert "mistral-v1" in rendered
    assert "namespace: flint" in rendered


def test_render_service_template() -> None:
    ctx = _ctx()
    rendered = render_template("vllm/service.yaml.j2", ctx)
    assert "kind: Service" in rendered
    assert "mistral-v1" in rendered


def test_render_hpa_template() -> None:
    ctx = _ctx()
    rendered = render_template("vllm/hpa.yaml.j2", ctx)
    assert "HorizontalPodAutoscaler" in rendered


def test_render_pvc_template() -> None:
    ctx = _ctx()
    rendered = render_template("vllm/pvc.yaml.j2", ctx)
    assert "PersistentVolumeClaim" in rendered
    assert "mistral-weights" in rendered


def test_render_missing_template_raises() -> None:
    ctx = _ctx()
    with pytest.raises(TemplateRenderError, match="not found"):
        render_template("vllm/nonexistent.yaml.j2", ctx)


def test_render_with_custom_dir(tmp_path: Path) -> None:
    (tmp_path / "test.yaml.j2").write_text("name: {{ model_name }}")
    ctx = _ctx()
    result = render_template("test.yaml.j2", ctx, templates_dir=tmp_path)
    assert result == "name: mistral"


def test_render_strict_undefined_raises_on_missing_var(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml.j2").write_text("{{ undefined_variable }}")
    ctx = _ctx()
    with pytest.raises(TemplateRenderError, match="Failed to render"):
        render_template("bad.yaml.j2", ctx, templates_dir=tmp_path)


# -- render_template_to_file --------------------------------------------------


def test_render_template_to_file(tmp_path: Path) -> None:
    ctx = _ctx()
    out = tmp_path / "out.yaml"
    render_template_to_file("vllm/service.yaml.j2", ctx, out)
    assert out.exists()
    content = out.read_text()
    assert "kind: Service" in content


def test_render_template_to_file_creates_parents(tmp_path: Path) -> None:
    ctx = _ctx()
    out = tmp_path / "nested" / "dir" / "out.yaml"
    render_template_to_file("vllm/service.yaml.j2", ctx, out)
    assert out.exists()


# -- render_deployment_templates ----------------------------------------------


def test_render_deployment_templates_returns_paths(tmp_path: Path) -> None:
    ctx = _ctx()
    paths = render_deployment_templates(ctx, tmp_path)
    assert len(paths) >= 3
    for p in paths:
        assert p.exists()
        assert p.suffix == ".yaml"


def test_render_deployment_templates_filenames(tmp_path: Path) -> None:
    ctx = _ctx()
    paths = render_deployment_templates(ctx, tmp_path)
    names = [p.name for p in paths]
    assert any("deployment" in n for n in names)
    assert any("service" in n for n in names)


def test_render_deployment_templates_missing_runtime_skips(tmp_path: Path) -> None:
    ctx = _ctx(runtime="nonexistent_runtime_xyz")
    paths = render_deployment_templates(ctx, tmp_path)
    assert paths == []
