"""Route contract tests for all read endpoints (GET /health, /info, /api/v1/*)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ── GET /health ───────────────────────────────────────────────────────────────


@patch(
    "growatt_bridge.routes.health.growatt_host_reachable",
    return_value=(True, None),
)
async def test_health_ok(_mock_reach, async_client):
    ac, mock_client, settings, safety = async_client

    resp = await ac.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["cloud_reachable"] is True
    assert data["cloud_error"] is None


@patch(
    "growatt_bridge.routes.health.growatt_host_reachable",
    return_value=(False, "connection refused"),
)
async def test_health_degraded_on_cloud_error(_mock_reach, async_client):
    ac, mock_client, settings, safety = async_client

    resp = await ac.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["cloud_reachable"] is False
    assert "connection refused" in (data["cloud_error"] or "")


# ── GET /info ─────────────────────────────────────────────────────────────────


async def test_info_readonly_default(async_client):
    ac, mock_client, settings, safety = async_client

    resp = await ac.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["readonly"] is True
    assert data["allowed_write_operations"] == []


async def test_info_with_write_allowlist(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from tests.conftest import make_app, make_mock_client, make_settings  # noqa: F401

    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_ac_charge_stop_soc",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    mock_client = make_mock_client()
    app, _ = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["readonly"] is False
        assert data["allowed_write_operations"] == ["set_ac_charge_stop_soc"]


# ── GET /api/v1/plants ────────────────────────────────────────────────────────


async def test_list_plants_ok(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.plant_list.return_value = [
        {"plant_id": "plant-1", "plantName": "Home Solar", "currentPower": "5000"},
        {"plantId": "plant-2", "plantName": "Office"},
    ]

    resp = await ac.get("/api/v1/plants")
    assert resp.status_code == 200
    plants = resp.json()
    assert len(plants) == 2
    assert plants[0]["plant_id"] == "plant-1"
    assert plants[0]["plant_name"] == "Home Solar"
    assert plants[0]["total_power"] == 5000.0


async def test_list_plants_cloud_error(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.plant_list.side_effect = RuntimeError("upstream timeout")

    resp = await ac.get("/api/v1/plants")
    assert resp.status_code == 502


async def test_list_plants_empty(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.plant_list.return_value = []

    resp = await ac.get("/api/v1/plants")
    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /api/v1/plants/{plant_id} ─────────────────────────────────────────────


async def test_get_plant_ok(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.plant_details.return_value = {
        "plant_id": "plant-1",
        "plantName": "Home Solar",
        "currentPower": "3500",
    }

    resp = await ac.get("/api/v1/plants/plant-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plant_id"] == "plant-1"
    assert data["plant_name"] == "Home Solar"
    assert data["total_power"] == 3500.0


async def test_get_plant_not_found(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.plant_details.return_value = {}

    resp = await ac.get("/api/v1/plants/nonexistent")
    assert resp.status_code == 404


async def test_get_plant_cloud_error(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.plant_details.side_effect = RuntimeError("bad gateway")

    resp = await ac.get("/api/v1/plants/plant-1")
    assert resp.status_code == 502


# ── GET /api/v1/plants/{plant_id}/devices ─────────────────────────────────────


async def test_list_plant_devices(async_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.device_list.return_value = [
        {"device_sn": "INV001", "deviceType": "7", "plant_id": "plant-1"},
    ]
    mock_client.detect_device_family.return_value = DeviceFamily.MIN

    resp = await ac.get("/api/v1/plants/plant-1/devices")
    assert resp.status_code == 200
    devices = resp.json()
    assert len(devices) == 1
    assert devices[0]["device_sn"] == "INV001"
    assert devices[0]["family"] == "MIN"


async def test_list_plant_devices_cloud_error(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.device_list.side_effect = RuntimeError("timeout")

    resp = await ac.get("/api/v1/plants/plant-1/devices")
    assert resp.status_code == 502


# ── GET /api/v1/devices/{sn} ──────────────────────────────────────────────────


async def test_get_device_ok(async_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.device_detail.return_value = {
        "device_sn": "INV001",
        "deviceType": "7",
        "plant_id": "plant-1",
        "deviceModel": "MOD 12KTL3-HU",
    }

    resp = await ac.get("/api/v1/devices/INV001?plant_id=plant-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["device_sn"] == "INV001"
    assert data["family"] == "MIN"


async def test_get_device_no_plant_id_scans_plants(async_client):
    """Without plant_id param, bridge should scan plant list to resolve it."""
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.plant_list.return_value = [{"plant_id": "plant-1"}]
    mock_client.device_list.return_value = [{"device_sn": "INV001", "deviceType": "7"}]
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.device_detail.return_value = {"device_sn": "INV001", "deviceType": "7"}

    resp = await ac.get("/api/v1/devices/INV001")
    assert resp.status_code == 200


async def test_get_device_not_found(async_client):
    ac, mock_client, settings, safety = async_client
    mock_client.plant_list.return_value = [{"plant_id": "plant-1"}]
    mock_client.device_list.return_value = []

    resp = await ac.get("/api/v1/devices/UNKNOWN_SN")
    assert resp.status_code == 404


# ── GET /api/v1/devices/{sn}/capabilities ─────────────────────────────────────


async def test_get_device_capabilities_readonly(async_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN

    resp = await ac.get("/api/v1/devices/INV001/capabilities?plant_id=plant-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["readonly"] is True
    assert data["supported_write_operations"] == []
    assert "telemetry" in data["supported_read_operations"]
    assert "config" in data["supported_read_operations"]


async def test_get_device_capabilities_write_mode(tmp_path):
    from growatt_bridge.client import DeviceFamily
    from httpx import ASGITransport, AsyncClient
    from tests.conftest import make_app, make_mock_client, make_settings

    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_ac_charge_stop_soc",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    mock_client = make_mock_client(family=DeviceFamily.MIN)
    app, _ = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/devices/INV001/capabilities?plant_id=plant-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["readonly"] is False
        assert data["supported_write_operations"] == ["set_ac_charge_stop_soc"]


# ── GET /api/v1/devices/{sn}/telemetry ────────────────────────────────────────


async def test_get_telemetry_cache_control(async_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.device_detail.return_value = {
        "device_sn": "INV001",
        "deviceType": "7",
        "ppv": 1000.0,
    }

    resp = await ac.get("/api/v1/devices/INV001/telemetry?plant_id=plant-1")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "private, max-age=300"
    assert resp.json()["device_sn"] == "INV001"
    assert mock_client.device_detail.call_count == 1


async def test_get_telemetry_server_cache_second_hit_skips_upstream(async_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.device_detail.return_value = {
        "device_sn": "INV001",
        "deviceType": "7",
        "ppv": 1000.0,
    }

    r1 = await ac.get("/api/v1/devices/INV001/telemetry?plant_id=plant-1")
    r2 = await ac.get("/api/v1/devices/INV001/telemetry?plant_id=plant-1")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert mock_client.device_detail.call_count == 1


async def test_get_telemetry_upstream_error_not_cached(async_client):
    from growatt_bridge.client import DeviceFamily

    ac, mock_client, settings, safety = async_client
    mock_client.detect_device_family.return_value = DeviceFamily.MIN
    mock_client.device_detail.side_effect = [RuntimeError("timeout"), RuntimeError("timeout")]

    r1 = await ac.get("/api/v1/devices/INV001/telemetry?plant_id=plant-1")
    r2 = await ac.get("/api/v1/devices/INV001/telemetry?plant_id=plant-1")
    assert r1.status_code == 502
    assert r2.status_code == 502
    assert mock_client.device_detail.call_count == 2
