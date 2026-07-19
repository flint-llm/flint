"""Tests for flint.core.build."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from flint.core.build import pull_image, push_image
from flint.core.errors import BuildError

# -- push_image ---------------------------------------------------------------


def test_push_image_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        push_image("docker.io/org/model:v1")
    cmd: str = mock_run.call_args[0][0]
    assert "docker push" in cmd
    assert "model:v1" in cmd


def test_push_image_failure_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="unauthorized: access denied"
        )
        with pytest.raises(BuildError, match="docker push failed"):
            push_image("docker.io/org/model:v1")


def test_push_image_error_message_contains_ref() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        with pytest.raises(BuildError, match="my-image:tag"):
            push_image("my-image:tag")


# -- pull_image ---------------------------------------------------------------


def test_pull_image_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        pull_image("vllm/vllm-openai:latest")
    cmd: str = mock_run.call_args[0][0]
    assert "docker pull" in cmd
    assert "vllm-openai" in cmd


def test_pull_image_failure_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="manifest not found"
        )
        with pytest.raises(BuildError, match="docker pull failed"):
            pull_image("vllm/vllm-openai:latest")
