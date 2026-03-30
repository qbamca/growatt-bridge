"""Tests for tokenless Growatt host reachability."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from growatt_bridge.connectivity import growatt_host_reachable


@patch("growatt_bridge.connectivity.requests.get")
def test_growatt_host_reachable_on_http_success(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_get.return_value = mock_resp

    ok, err = growatt_host_reachable("https://openapi.growatt.com")

    assert ok is True
    assert err is None
    mock_get.assert_called_once()
    call_kw = mock_get.call_args[1]
    assert call_kw.get("stream") is True
    mock_resp.close.assert_called_once()


@patch("growatt_bridge.connectivity.requests.get")
def test_growatt_host_unreachable_on_request_error(mock_get: MagicMock) -> None:
    mock_get.side_effect = requests.ConnectionError("connection refused")

    ok, err = growatt_host_reachable("https://openapi.growatt.com/")

    assert ok is False
    assert err is not None
    assert "connection refused" in err
