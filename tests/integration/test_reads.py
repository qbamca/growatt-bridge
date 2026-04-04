"""Integration tests for all read (GET) endpoints.

These tests are safe to run at any time — they make no writes to the inverter.
Each test asserts HTTP 200 and the expected response shape.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.integration


async def test_health(live_app_client: AsyncClient) -> None:
    r = await live_app_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "cloud_reachable" in body


async def test_info(live_app_client: AsyncClient) -> None:
    r = await live_app_client.get("/info")
    assert r.status_code == 200
    body = r.json()
    assert "readonly" in body
    assert isinstance(body["allowed_write_operations"], list)


async def test_plants_list(live_app_client: AsyncClient) -> None:
    r = await live_app_client.get("/api/v1/plants")
    assert r.status_code == 200
    plants = r.json()
    assert isinstance(plants, list)
    assert len(plants) > 0, "expected at least one plant"
    assert "plant_id" in plants[0]
    assert "plant_name" in plants[0]


async def test_plant_detail(live_app_client: AsyncClient, plant_id: str | None) -> None:
    if not plant_id:
        pytest.skip("GROWATT_PLANT_ID not set")
    r = await live_app_client.get(f"/api/v1/plants/{plant_id}")
    assert r.status_code == 200
    body = r.json()
    assert body.get("plant_id") == plant_id


async def test_devices_in_plant(live_app_client: AsyncClient, plant_id: str | None) -> None:
    if not plant_id:
        pytest.skip("GROWATT_PLANT_ID not set")
    r = await live_app_client.get(f"/api/v1/plants/{plant_id}/devices")
    assert r.status_code == 200
    devices = r.json()
    assert isinstance(devices, list)
    assert len(devices) > 0, "expected at least one device in plant"


async def test_device_detail(live_app_client: AsyncClient, device_sn: str) -> None:
    r = await live_app_client.get(f"/api/v1/devices/{device_sn}")
    assert r.status_code == 200
    body = r.json()
    assert body.get("device_sn") == device_sn
    assert "family" in body


async def test_device_capabilities(live_app_client: AsyncClient, device_sn: str) -> None:
    r = await live_app_client.get(f"/api/v1/devices/{device_sn}/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert "supported_read_operations" in body
    assert "supported_write_operations" in body


async def test_telemetry(live_app_client: AsyncClient, device_sn: str) -> None:
    r = await live_app_client.get(f"/api/v1/devices/{device_sn}/telemetry")
    assert r.status_code == 200
    body = r.json()
    assert body.get("device_sn") == device_sn
    assert "timestamp" in body


async def test_config_snapshot(live_app_client: AsyncClient, device_sn: str) -> None:
    r = await live_app_client.get(f"/api/v1/devices/{device_sn}/config")
    assert r.status_code == 200
    body = r.json()
    assert body.get("device_sn") == device_sn
    assert "time_segments" in body
    assert isinstance(body["time_segments"], list)


async def test_time_segments(live_app_client: AsyncClient, device_sn: str) -> None:
    r = await live_app_client.get(f"/api/v1/devices/{device_sn}/config/time-segments")
    assert r.status_code == 200
    segments = r.json()
    assert isinstance(segments, list)
    for seg in segments:
        assert "segment" in seg
        assert "mode" in seg
        assert "start_time" in seg
        assert "end_time" in seg
        assert "enabled" in seg
