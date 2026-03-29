"""Route contract tests for write command endpoints.

POST /api/v1/devices/{sn}/commands/{operation_id}
POST /api/v1/devices/{sn}/commands/{operation_id}/validate

All Growatt Cloud calls are intercepted by the mock_client from conftest.
"""

from __future__ import annotations

import pytest


# ── POST /commands/{op} — readonly mode ───────────────────────────────────────


async def test_execute_command_readonly_returns_403(async_client):
    ac, mock_client, settings, safety = async_client
    # Default fixture has bridge_readonly=True

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power?plant_id=plant-1",
        json={"params": {"value": 75}},
    )
    assert resp.status_code == 403
    assert "readonly" in resp.json()["detail"].lower()


# ── POST /commands/{op} — unknown operation ───────────────────────────────────


async def test_execute_command_unknown_op_returns_404(async_client):
    ac, mock_client, settings, safety = async_client

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/totally_unknown_op?plant_id=plant-1",
        json={"params": {}},
    )
    assert resp.status_code == 404


# ── POST /commands/{op} — validation error ────────────────────────────────────


async def test_execute_command_bad_params_returns_422(write_client):
    ac, mock_client, settings, safety = write_client

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power?plant_id=plant-1",
        json={"params": {"value": 999}},  # out of range
    )
    assert resp.status_code == 422


# ── POST /commands/{op} — success ────────────────────────────────────────────


async def test_execute_command_success(write_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = write_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.min_write_parameter.return_value = {"result_code": "1", "result_msg": "success"}

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power?plant_id=plant-1",
        json={"params": {"value": 75}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["operation"] == "set_charge_power"
    assert data["device_sn"] == "INV001"
    assert data["audit_id"]


async def test_execute_command_success_includes_params_sent(write_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = write_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.min_write_parameter.return_value = {"result_code": "1"}

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power?plant_id=plant-1",
        json={"params": {"value": 50}},
    )
    data = resp.json()
    assert "params_sent" in data
    assert data["params_sent"]["value"] == 50


# ── POST /commands/set_time_segment ──────────────────────────────────────────


async def test_execute_time_segment_success(write_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = write_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.min_write_time_segment.return_value = {"result_code": "1"}

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_time_segment?plant_id=plant-1",
        json={"params": {"segment": 1, "mode": 1, "start_time": "22:00", "end_time": "06:00"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["operation"] == "set_time_segment"


async def test_execute_time_segment_bad_segment_returns_422(write_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = write_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_time_segment?plant_id=plant-1",
        json={"params": {"segment": 99, "mode": 1, "start_time": "22:00", "end_time": "06:00"}},
    )
    assert resp.status_code == 422


# ── POST /commands/set_export_limit — meter guard ─────────────────────────────


async def test_export_limit_without_meter_acknowledged_returns_422(tmp_path):
    from growatt_bridge.client import DeviceFamily
    from httpx import ASGITransport, AsyncClient
    from tests.conftest import make_app, make_mock_client, make_settings

    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_export_limit",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    mock_client = make_mock_client(family=DeviceFamily.MIN)
    mock_client.min_write_parameter.return_value = {"result_code": "1"}
    app, _ = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/devices/INV001/commands/set_export_limit?plant_id=plant-1",
            json={"params": {"value": 50}},  # missing meter_acknowledged
        )
        assert resp.status_code == 422
        assert "meter_acknowledged" in str(resp.json())


# ── POST /commands/{op}/validate — dry-run ────────────────────────────────────


async def test_validate_command_valid(write_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = write_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power/validate?plant_id=plant-1",
        json={"params": {"value": 80}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []
    assert data["operation"] == "set_charge_power"
    # Confirm the mock was NOT called for actual write
    mock_client.min_write_parameter.assert_not_called()


async def test_validate_command_invalid_params(write_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = write_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power/validate?plant_id=plant-1",
        json={"params": {"value": 200}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["errors"]


async def test_validate_command_unknown_op(write_client):
    ac, mock_client, settings, safety = write_client

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/not_real_op/validate?plant_id=plant-1",
        json={"params": {}},
    )
    assert resp.status_code == 404


async def test_validate_command_readonly_mode_returns_invalid(async_client):
    """Dry-run in readonly mode returns valid=False but 200 status."""
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power/validate?plant_id=plant-1",
        json={"params": {"value": 75}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any("readonly" in e.lower() for e in data["errors"])


# ── POST /commands — API failure captured ─────────────────────────────────────


async def test_execute_command_api_failure_returns_200_with_success_false(write_client):
    """growattServer returning result_code=0 is not an HTTP error — it's a CommandResponse with success=False."""
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = write_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.min_write_parameter.return_value = {"result_code": "0", "result_msg": "bad request"}

    resp = await ac.post(
        "/api/v1/devices/INV001/commands/set_charge_power?plant_id=plant-1",
        json={"params": {"value": 75}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"]


# ── POST /commands — discharge SOC floor ──────────────────────────────────────


async def test_discharge_stop_soc_zero_rejected(tmp_path):
    from growatt_bridge.client import DeviceFamily
    from httpx import ASGITransport, AsyncClient
    from tests.conftest import make_app, make_mock_client, make_settings

    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_discharge_stop_soc",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    mock_client = make_mock_client(family=DeviceFamily.MIN)
    app, _ = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/devices/INV001/commands/set_discharge_stop_soc?plant_id=plant-1",
            json={"params": {"value": 0}},
        )
        assert resp.status_code == 422
        mock_client.min_write_parameter.assert_not_called()
