"""Shared test fixtures for growatt-bridge tests.

growattServer is mocked at the sys.modules level so tests never make real
API calls and the package does not need to be importable from within tests.
The mock is installed before any bridge module imports to satisfy the
import-guard in client.py.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Mock growattServer before bridge modules are imported ─────────────────────
# client.py guards against a missing growattServer with an import-time check.
# We install a MagicMock so that guard passes and _api calls are interceptable.
_mock_growatt_module = MagicMock()
_mock_openapi_instance = MagicMock()
_mock_growatt_module.OpenApiV1.return_value = _mock_openapi_instance
sys.modules.setdefault("growattServer", _mock_growatt_module)

# ── Bridge imports (after mock is in place) ───────────────────────────────────
from growatt_bridge.client import DeviceFamily, GrowattClient  # noqa: E402
from growatt_bridge.config import Settings  # noqa: E402
from growatt_bridge.main import create_app  # noqa: E402
from growatt_bridge.safety import SafetyLayer  # noqa: E402


# ── Settings factory ──────────────────────────────────────────────────────────


def make_settings(**overrides) -> Settings:
    """Construct a Settings instance with test-safe defaults."""
    defaults = dict(
        growatt_api_token="test-token-1234",
        growatt_server_url="https://openapi.growatt.com/",
        growatt_device_sn=None,
        growatt_plant_id=None,
        bridge_port=8081,
        bridge_host="0.0.0.0",
        bridge_readonly=True,
        bridge_write_allowlist="",
        bridge_rate_limit_writes=3,
        bridge_require_readback=True,
        bridge_audit_log=Path("/tmp/test-audit.jsonl"),
    )
    defaults.update(overrides)
    return Settings.model_validate(defaults)


# ── GrowattClient mock factory ────────────────────────────────────────────────


def make_mock_client(
    family: DeviceFamily = DeviceFamily.MIN,
    plants: list | None = None,
    devices: list | None = None,
) -> MagicMock:
    """Return a MagicMock GrowattClient pre-configured with sensible defaults."""
    if plants is None:
        plants = [{"plant_id": "plant-1", "plantName": "Test Plant", "currentPower": "5000"}]
    if devices is None:
        devices = [{"device_sn": "INV001", "deviceType": "7", "plant_id": "plant-1"}]

    client = MagicMock(spec=GrowattClient)
    client.plant_list.return_value = plants
    client.plant_details.return_value = plants[0] if plants else {}
    client.device_list.return_value = devices
    client.detect_device_family.return_value = family
    client.device_detail.return_value = {
        "device_sn": "INV001",
        "deviceType": "7",
        "plant_id": "plant-1",
    }
    client.read_time_segments.return_value = []
    return client


# ── App fixture with injected mock state ──────────────────────────────────────


def make_app(settings: Settings, mock_client: MagicMock) -> tuple:
    """Create a FastAPI app with state pre-populated for tests.

    ``ASGITransport`` does not trigger ASGI lifespan events, so we bypass
    the lifespan entirely by setting ``app.state`` directly.  The routes
    access ``request.app.state``, which is the same object.

    Returns (app, safety).
    """
    safety = SafetyLayer(settings, mock_client)
    app = create_app()
    app.state.settings = settings
    app.state.client = mock_client
    app.state.safety = safety
    return app, safety


@pytest_asyncio.fixture
async def async_client(tmp_path):
    """AsyncClient wired to a test app with mocked Growatt state."""
    settings = make_settings(bridge_audit_log=tmp_path / "audit.jsonl")
    mock_client = make_mock_client()
    app, safety = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_client, settings, safety


@pytest_asyncio.fixture
async def write_client(tmp_path):
    """AsyncClient with writes enabled (set_charge_power allowlisted)."""
    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_charge_power,set_discharge_stop_soc,set_time_segment",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    mock_client = make_mock_client()
    mock_client.min_write_parameter.return_value = {"result_code": "1", "result_msg": "success"}
    mock_client.min_write_time_segment.return_value = {"result_code": "1", "result_msg": "success"}
    app, safety = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_client, settings, safety
