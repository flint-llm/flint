"""Tests for the flint deploy command (unit — core mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from flint.cli.main import cli
from flint.config import FlintConfig
from flint.core.errors import K8sError
from flint.core.models import DeployResult


def _result(**kw: object) -> DeployResult:
    base: dict[str, object] = {
        "model_name": "mistral",
        "model_version": "latest",
        "namespace": "flint",
        "applied_manifests": [Path("mistral-latest-deployment.yaml")],
        "endpoint": "http://mistral-latest.flint.svc.cluster.local/v1",
        "ready": False,
    }
    base.update(kw)
    return DeployResult(**base)  # type: ignore[arg-type]


# -- happy path + defaults ----------------------------------------------------


def test_deploy_prints_endpoint() -> None:
    with patch("flint.cli.deploy.deploy_model", return_value=_result()) as mock_deploy:
        result = CliRunner().invoke(cli, ["deploy", "mistral"])
    assert result.exit_code == 0, result.output
    assert "Deployed mistral:latest" in result.output
    assert "svc.cluster.local/v1" in result.output
    ctx = mock_deploy.call_args.args[0]
    assert ctx.model_name == "mistral"
    assert ctx.runtime == "vllm"      # built-in default
    assert ctx.namespace == "flint"   # built-in default


def test_deploy_registered_in_group() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert "deploy" in result.output


# -- flag precedence / threading ----------------------------------------------


def test_deploy_runtime_namespace_replicas_override() -> None:
    with patch("flint.cli.deploy.deploy_model", return_value=_result()) as mock_deploy:
        result = CliRunner().invoke(
            cli,
            ["deploy", "mistral", "--namespace", "prod", "--replicas", "3"],
        )
    assert result.exit_code == 0, result.output
    ctx = mock_deploy.call_args.args[0]
    assert ctx.namespace == "prod"
    assert ctx.replicas == 3


def test_deploy_gpu_and_resource_overrides() -> None:
    with patch("flint.cli.deploy.deploy_model", return_value=_result()) as mock_deploy:
        CliRunner().invoke(
            cli,
            ["deploy", "m", "--gpu", "2", "--cpu-limit", "8000m", "--memory-limit", "16Gi"],
        )
    ctx = mock_deploy.call_args.args[0]
    assert ctx.resources.gpu_count == 2
    assert ctx.resources.cpu_limit == "8000m"
    assert ctx.resources.memory_limit == "16Gi"
    assert ctx.resources.cpu_request == "500m"  # default preserved


def test_deploy_threads_hf_options() -> None:
    with patch("flint.cli.deploy.deploy_model", return_value=_result()) as mock_deploy:
        CliRunner().invoke(
            cli,
            ["deploy", "m", "--hf-repo", "org/m", "--hf-token-secret", "hf-tok"],
        )
    ctx = mock_deploy.call_args.args[0]
    assert ctx.hf_repo == "org/m"
    assert ctx.hf_token_secret == "hf-tok"


def test_deploy_custom_image_used() -> None:
    with patch("flint.cli.deploy.deploy_model", return_value=_result()) as mock_deploy:
        CliRunner().invoke(cli, ["deploy", "m", "--image", "my/img:1"])
    ctx = mock_deploy.call_args.args[0]
    assert ctx.image == "my/img:1"


# -- config fallback ----------------------------------------------------------


def test_deploy_uses_config_default_model_when_arg_omitted() -> None:
    with (
        patch("flint.cli.deploy.load_config", return_value=FlintConfig(default_model="cfg-model")),
        patch("flint.cli.deploy.deploy_model", return_value=_result(model_name="cfg-model")) as mock_deploy,
    ):
        result = CliRunner().invoke(cli, ["deploy"])
    assert result.exit_code == 0, result.output
    ctx = mock_deploy.call_args.args[0]
    assert ctx.model_name == "cfg-model"


def test_deploy_missing_model_errors() -> None:
    with patch("flint.cli.deploy.load_config", return_value=FlintConfig()):
        result = CliRunner().invoke(cli, ["deploy"])
    assert result.exit_code != 0
    assert "No model specified" in result.output


# -- wait + errors ------------------------------------------------------------


def test_deploy_wait_flag_forwarded_and_reported() -> None:
    with patch("flint.cli.deploy.deploy_model", return_value=_result(ready=True)) as mock_deploy:
        result = CliRunner().invoke(cli, ["deploy", "m", "--wait"])
    assert mock_deploy.call_args.kwargs["wait"] is True
    assert "ready" in result.output


def test_deploy_flint_error_no_traceback() -> None:
    with patch("flint.cli.deploy.deploy_model", side_effect=K8sError("apply failed")):
        result = CliRunner().invoke(cli, ["deploy", "m"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "apply failed" in result.output
