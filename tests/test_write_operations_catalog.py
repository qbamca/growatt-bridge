"""Tests for GET /api/v1/write-operations."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from growatt_bridge.safety import OPERATION_REGISTRY, build_write_operations_catalog
from tests.conftest import make_app, make_mock_client, make_settings


def test_build_catalog_matches_registry_keys():
    data = build_write_operations_catalog(include_policy=False, settings=None)
    ids = {op["operation_id"] for op in data["operations"]}
    assert ids == set(OPERATION_REGISTRY.keys()) == {"set_ac_charge_stop_soc"}


def test_build_catalog_scalar_schema():
    data = build_write_operations_catalog(include_policy=False, settings=None)
    op = data["operations"][0]
    assert op["operation_id"] == "set_ac_charge_stop_soc"
    assert op["constraints"]["requires_meter_acknowledgment"] is False
    fields = op["params_schema"]["fields"]
    assert len(fields) == 1
    assert fields[0]["name"] == "value"
    assert fields[0]["min"] == 10
    assert fields[0]["max"] == 100


@pytest.mark.asyncio
async def test_get_write_operations_no_policy(async_client):
    ac, mock_client, settings, safety = async_client

    resp = await ac.get("/api/v1/write-operations")
    assert resp.status_code == 200
    body = resp.json()
    assert "readonly" not in body
    assert body.get("allowlist_parse_error") is None
    assert len(body["operations"]) == 1
    first = body["operations"][0]
    assert "currently_permitted" not in first


@pytest.mark.asyncio
async def test_get_write_operations_include_policy_readonly(async_client):
    ac, mock_client, settings, safety = async_client

    resp = await ac.get("/api/v1/write-operations", params={"include_policy": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["readonly"] is True
    assert body.get("allowlist_parse_error") in (None, "")
    for op in body["operations"]:
        assert op["currently_permitted"] is False


@pytest.mark.asyncio
async def test_get_write_operations_include_policy_allowlisted(tmp_path):
    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_ac_charge_stop_soc",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    mock_client = make_mock_client()
    app, _ = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/write-operations", params={"include_policy": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["readonly"] is False
    assert body["operations"][0]["currently_permitted"] is True


@pytest.mark.asyncio
async def test_get_write_operations_invalid_allowlist(tmp_path):
    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="not_a_real_operation",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    mock_client = make_mock_client()
    app, _ = make_app(settings, mock_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/write-operations", params={"include_policy": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowlist_parse_error"]
    for op in body["operations"]:
        assert op["currently_permitted"] is False
