"""Tests for flint.core.cluster."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flint.core.cluster import (
    _extract_lb_address,
    _get_ingress_ip,
    _get_ingress_nodeport,
    ensure_namespace,
    has_gateway_api,
)
from flint.core.errors import ClusterError

# -- _extract_lb_address (pure) -----------------------------------------------


def _lb_status(hostname: str | None = None, ip: str | None = None) -> object:
    entry = SimpleNamespace(hostname=hostname, ip=ip)
    lb = SimpleNamespace(ingress=[entry])
    return SimpleNamespace(load_balancer=lb)


def test_extract_lb_hostname() -> None:
    status = _lb_status(hostname="my-lb.example.com")
    assert _extract_lb_address(status) == "my-lb.example.com"


def test_extract_lb_ip() -> None:
    status = _lb_status(ip="1.2.3.4")
    assert _extract_lb_address(status) == "1.2.3.4"


def test_extract_lb_hostname_takes_priority() -> None:
    status = _lb_status(hostname="host.example.com", ip="1.2.3.4")
    assert _extract_lb_address(status) == "host.example.com"


def test_extract_lb_empty_list() -> None:
    status = SimpleNamespace(load_balancer=SimpleNamespace(ingress=[]))
    assert _extract_lb_address(status) is None


def test_extract_lb_none_status() -> None:
    assert _extract_lb_address(None) is None


def test_extract_lb_attribute_error() -> None:
    assert _extract_lb_address(SimpleNamespace()) is None


# -- has_gateway_api ----------------------------------------------------------


def test_has_gateway_api_true() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert has_gateway_api() is True


def test_has_gateway_api_false() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert has_gateway_api() is False


# -- ensure_namespace ---------------------------------------------------------


def test_ensure_namespace_exists_skips() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ensure_namespace("flint")
    mock_run.assert_called_once()


def test_ensure_namespace_missing_creates() -> None:
    responses = [
        MagicMock(returncode=1),
        MagicMock(returncode=0, stderr=""),
    ]
    with patch("subprocess.run", side_effect=responses):
        ensure_namespace("new-ns")


def test_ensure_namespace_create_fails_raises() -> None:
    responses = [
        MagicMock(returncode=1),
        MagicMock(returncode=1, stderr="forbidden"),
    ]
    with patch("subprocess.run", side_effect=responses):
        with pytest.raises(ClusterError, match="Failed to create namespace"):
            ensure_namespace("bad-ns")


# -- _get_ingress_nodeport ----------------------------------------------------


def test_get_ingress_nodeport_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="30080", text=True)
        result = _get_ingress_nodeport()
    assert result == "30080"


def test_get_ingress_nodeport_failure_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with pytest.raises(ClusterError, match="NodePort"):
            _get_ingress_nodeport()


# -- _get_ingress_ip ----------------------------------------------------------


def test_get_ingress_ip_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="192.168.1.1")
        result = _get_ingress_ip()
    assert result == "192.168.1.1"


def test_get_ingress_ip_failure_raises() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with pytest.raises(ClusterError, match="IP"):
            _get_ingress_ip()
