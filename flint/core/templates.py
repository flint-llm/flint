"""Jinja2 template rendering for Kubernetes manifests.

All templates live inside the flint package at flint/templates/.
The default template root can be overridden per-project via flint.toml:

    [templates]
    dir = "./my-flint-templates"

Templates receive a RenderContext converted to a flat dict, plus shortcuts
for commonly accessed nested fields (cpu_limit, gpu_count, etc.).

Ported from monolith: _create_predict_kube_Kubernetes_yaml (lines 981-1104),
_templates_path (lines 296-301), _set_dataspine_templates_path (lines 848-856).
"""

from __future__ import annotations

from pathlib import Path

import jinja2

from flint.core.errors import TemplateRenderError
from flint.core.models import RenderContext


def get_templates_dir() -> Path:
    """Return the path to the built-in template directory inside the package."""
    return Path(__file__).parent.parent / "templates"


def resolve_templates_path(templates_path: str | Path | None = None) -> Path:
    """Resolve and normalise a templates directory path.

    Falls back to the built-in templates dir if *templates_path* is None.
    Raises TemplateRenderError if the resolved path is not a directory.

    Ported from monolith _set_dataspine_templates_path (lines 848-856).
    """
    if templates_path is None:
        return get_templates_dir()
    resolved = Path(templates_path).expanduser().resolve()
    if not resolved.is_dir():
        raise TemplateRenderError(f"Templates directory not found: {resolved}")
    return resolved


def render_template(
    template_name: str,
    context: RenderContext,
    templates_dir: Path | None = None,
) -> str:
    """Render a Jinja2 template and return the result as a string.

    Args:
        template_name: Relative path inside the templates directory,
            e.g. ``"vllm/deployment.yaml.j2"``.
        context: Validated RenderContext with all template variables.
        templates_dir: Override the built-in templates directory.

    Raises:
        TemplateRenderError: If the template is not found or rendering fails.
    """
    resolved_dir = resolve_templates_path(templates_dir)
    env = _build_env(resolved_dir)
    try:
        tmpl = env.get_template(template_name)
    except jinja2.TemplateNotFound as exc:
        raise TemplateRenderError(
            f"Template not found: {template_name!r} in {resolved_dir}"
        ) from exc

    flat = _flatten_context(context)
    try:
        return tmpl.render(**flat)
    except jinja2.TemplateError as exc:
        raise TemplateRenderError(
            f"Failed to render {template_name!r}: {exc}"
        ) from exc


def render_template_to_file(
    template_name: str,
    context: RenderContext,
    output_path: Path,
    templates_dir: Path | None = None,
) -> None:
    """Render *template_name* and write the result to *output_path*."""
    rendered = render_template(template_name, context, templates_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")


def render_deployment_templates(
    context: RenderContext,
    output_dir: Path,
    runtime: str | None = None,
    templates_dir: Path | None = None,
) -> list[Path]:
    """Render all manifest templates for a deployment into *output_dir*.

    Returns a list of paths to the rendered YAML files. Templates that do
    not exist are silently skipped (e.g. pvc when using preloaded weights).

    Ported from monolith _create_predict_kube_Kubernetes_yaml (lines 981-1104).

    Args:
        context: Validated render context.
        output_dir: Directory where rendered YAML files are written.
        runtime: Override the runtime sub-directory (defaults to context.runtime).
        templates_dir: Override the built-in templates directory.
    """
    rt = runtime or context.runtime
    output_dir.mkdir(parents=True, exist_ok=True)

    template_names = [
        f"{rt}/deployment.yaml.j2",
        f"{rt}/service.yaml.j2",
        f"{rt}/hpa.yaml.j2",
        f"{rt}/pvc.yaml.j2",
    ]

    rendered_paths: list[Path] = []
    for tname in template_names:
        stem = tname.split("/")[-1].replace(".j2", "")
        out = output_dir / f"{context.model_name}-{context.model_version}-{stem}"
        try:
            render_template_to_file(tname, context, out, templates_dir)
            rendered_paths.append(out)
        except TemplateRenderError:
            # Template does not exist for this runtime/strategy; skip.
            pass

    return rendered_paths


# -- Private helpers -----------------------------------------------------------


def _build_env(templates_dir: Path) -> jinja2.Environment:
    """Build a Jinja2 Environment with strict undefined for *templates_dir*."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def _flatten_context(context: RenderContext) -> dict[str, object]:
    """Convert RenderContext to a flat dict for Jinja2 rendering.

    The flat dict includes both the full nested objects (accessible via
    dotted attribute syntax) and top-level shortcuts for commonly used fields.
    """
    flat: dict[str, object] = context.model_dump()
    flat["cpu_request"] = context.resources.cpu_request
    flat["cpu_limit"] = context.resources.cpu_limit
    flat["memory_request"] = context.resources.memory_request
    flat["memory_limit"] = context.resources.memory_limit
    flat["gpu_count"] = context.resources.gpu_count
    flat["gpu_type"] = context.resources.gpu_type
    flat["readiness_port"] = context.readiness_probe.port
    flat["readiness_path"] = context.readiness_probe.path
    flat["readiness_initial_delay"] = context.readiness_probe.initial_delay_seconds
    return flat
