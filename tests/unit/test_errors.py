"""Tests for flint.core.errors."""

import pytest

from flint.core.errors import (
    BuildError,
    ClusterError,
    FlintError,
    K8sError,
    ModelNotFoundError,
    RoutingError,
    TemplateRenderError,
    WeightsValidationError,
)


def test_flint_error_is_exception() -> None:
    assert issubclass(FlintError, Exception)


def test_all_errors_are_flint_errors() -> None:
    for cls in [
        TemplateRenderError,
        K8sError,
        ClusterError,
        ModelNotFoundError,
        RoutingError,
        BuildError,
        WeightsValidationError,
    ]:
        assert issubclass(cls, FlintError)


def test_errors_carry_message() -> None:
    for cls in [
        FlintError,
        TemplateRenderError,
        K8sError,
        ClusterError,
        ModelNotFoundError,
        RoutingError,
        BuildError,
        WeightsValidationError,
    ]:
        err = cls("test message")
        assert str(err) == "test message"


def test_errors_are_catchable_as_flint_error() -> None:
    with pytest.raises(FlintError):
        raise TemplateRenderError("boom")

    with pytest.raises(FlintError):
        raise K8sError("boom")

    with pytest.raises(FlintError):
        raise WeightsValidationError("boom")
