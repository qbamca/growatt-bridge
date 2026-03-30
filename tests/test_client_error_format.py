"""Tests for Growatt SDK error formatting (error_code / error_msg surfaced)."""

from __future__ import annotations

import growatt_bridge.client as client_mod
import pytest


class _StubGrowattV1ApiError(Exception):
    """Same shape as growattServer.exceptions.GrowattV1ApiError (tests use a mocked growattServer)."""

    def __init__(
        self,
        message: str,
        error_code: int | None = None,
        error_msg: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_msg = error_msg


@pytest.fixture(autouse=True)
def _register_stub_v1_error_on_mock_growatt_server() -> None:
    """conftest replaces growattServer with MagicMock; teach it our stub exception class."""
    client_mod.growattServer.GrowattV1ApiError = _StubGrowattV1ApiError  # type: ignore[attr-defined]
    yield


def test_format_growatt_v1_api_error_includes_code_and_msg() -> None:
    from growatt_bridge.client import format_growatt_cloud_error

    exc = _StubGrowattV1ApiError(
        "Error during getting plant list",
        error_code=10012,
        error_msg="error_frequently_access",
    )
    s = format_growatt_cloud_error(exc)
    assert "Error during getting plant list" in s
    assert "error_code=10012" in s
    assert "error_frequently_access" in s


def test_format_generic_exception_is_str() -> None:
    from growatt_bridge.client import format_growatt_cloud_error

    assert format_growatt_cloud_error(RuntimeError("upstream timeout")) == "upstream timeout"


@pytest.mark.asyncio
async def test_list_plants_502_includes_growatt_api_fields(async_client) -> None:
    ac, mock_client, settings, safety = async_client
    mock_client.plant_list.side_effect = _StubGrowattV1ApiError(
        "Error during getting plant list",
        error_code=10012,
        error_msg="error_frequently_access",
    )

    resp = await ac.get("/api/v1/plants")
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "10012" in detail
    assert "error_frequently_access" in detail
