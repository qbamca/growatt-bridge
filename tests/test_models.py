"""Tests for growatt_bridge.models (Pydantic model instantiation and normalization)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from growatt_bridge.models import (
    CommandRequest,
    CommandResponse,
    DeviceCapabilities,
    DeviceInfo,
    ErrorResponse,
    NormalizedConfig,
    NormalizedTelemetry,
    PlantDetail,
    PlantSummary,
    ReadbackDiff,
    TimeSegment,
    ValidateResponse,
)


# ── TimeSegment ───────────────────────────────────────────────────────────────


def test_time_segment_valid():
    seg = TimeSegment(segment=1, mode=0, start_time="08:00", end_time="20:00")
    assert seg.enabled is True  # default


def test_time_segment_segment_bounds():
    with pytest.raises(ValidationError):
        TimeSegment(segment=0, mode=0, start_time="08:00", end_time="20:00")
    with pytest.raises(ValidationError):
        TimeSegment(segment=10, mode=0, start_time="08:00", end_time="20:00")


def test_time_segment_mode_bounds():
    with pytest.raises(ValidationError):
        TimeSegment(segment=1, mode=3, start_time="08:00", end_time="20:00")
    with pytest.raises(ValidationError):
        TimeSegment(segment=1, mode=-1, start_time="08:00", end_time="20:00")


def test_time_segment_disabled():
    seg = TimeSegment(segment=5, mode=2, start_time="00:00", end_time="23:59", enabled=False)
    assert seg.enabled is False


# ── NormalizedTelemetry ───────────────────────────────────────────────────────


def test_normalized_telemetry_minimal():
    t = NormalizedTelemetry(device_sn="INV001")
    assert t.device_sn == "INV001"
    assert t.ppv is None
    assert t.soc is None
    assert t.lost is False
    assert isinstance(t.timestamp, datetime)


def test_normalized_telemetry_full():
    t = NormalizedTelemetry(
        device_sn="INV001",
        ppv=5000.0,
        pac=4800.0,
        soc=85.0,
        p_charge=1200.0,
        p_to_grid=300.0,
        e_today=20.5,
        status_code=1,
        status_text="Normal",
    )
    assert t.ppv == 5000.0
    assert t.soc == 85.0
    assert t.status_text == "Normal"


def test_normalized_telemetry_raw_excluded_from_serialisation():
    t = NormalizedTelemetry(device_sn="INV001", raw={"secret": "data"})
    dumped = t.model_dump()
    assert "raw" not in dumped


def test_normalized_telemetry_timestamp_utc():
    t = NormalizedTelemetry(device_sn="INV001")
    assert t.timestamp.tzinfo is not None


# ── NormalizedConfig ──────────────────────────────────────────────────────────


def test_normalized_config_empty():
    c = NormalizedConfig(device_sn="INV001")
    assert c.charge_power_rate is None
    assert c.time_segments == []


def test_normalized_config_with_segments():
    seg = TimeSegment(segment=1, mode=1, start_time="22:00", end_time="06:00")
    c = NormalizedConfig(device_sn="INV001", time_segments=[seg])
    assert len(c.time_segments) == 1
    assert c.time_segments[0].segment == 1


def test_normalized_config_raw_excluded():
    c = NormalizedConfig(device_sn="INV001", raw={"internal": True})
    assert "raw" not in c.model_dump()


# ── ReadbackDiff ──────────────────────────────────────────────────────────────


def test_readback_diff_defaults():
    diff = ReadbackDiff()
    assert diff.changed == {}
    assert diff.unchanged == []
    assert diff.readback_failed is False
    assert diff.readback_error is None


def test_readback_diff_with_changes():
    diff = ReadbackDiff(
        changed={"charge_power_rate": {"before": 80, "after": 75}},
        unchanged=["discharge_stop_soc"],
    )
    assert "charge_power_rate" in diff.changed
    assert "discharge_stop_soc" in diff.unchanged


def test_readback_diff_failed():
    diff = ReadbackDiff(readback_failed=True, readback_error="Timeout")
    assert diff.readback_failed is True
    assert diff.readback_error == "Timeout"


# ── CommandRequest ────────────────────────────────────────────────────────────


def test_command_request_empty_params():
    req = CommandRequest()
    assert req.params == {}


def test_command_request_with_params():
    req = CommandRequest(params={"value": 75})
    assert req.params["value"] == 75


# ── CommandResponse ───────────────────────────────────────────────────────────


def test_command_response_success():
    resp = CommandResponse(
        success=True,
        operation="set_ac_charge_stop_soc",
        device_sn="INV001",
        audit_id="uuid-1234",
    )
    assert resp.success is True
    assert resp.error is None
    assert resp.readback is None


def test_command_response_failure():
    resp = CommandResponse(
        success=False,
        operation="set_ac_charge_stop_soc",
        device_sn="INV001",
        audit_id="uuid-1234",
        error="API returned failure code: 0",
    )
    assert resp.success is False
    assert "API returned" in (resp.error or "")


# ── ValidateResponse ──────────────────────────────────────────────────────────


def test_validate_response_valid():
    v = ValidateResponse(
        valid=True,
        operation="set_ac_charge_stop_soc",
        device_sn="INV001",
        params={"value": 75},
    )
    assert v.valid is True
    assert v.errors == []


def test_validate_response_invalid():
    v = ValidateResponse(
        valid=False,
        operation="set_ac_charge_stop_soc",
        device_sn="INV001",
        params={"value": 200},
        errors=["'value' must be ≤ 100, got 200.0."],
    )
    assert v.valid is False
    assert v.errors


# ── DeviceInfo ────────────────────────────────────────────────────────────────


def test_device_info_minimal():
    d = DeviceInfo(device_sn="INV001", family="MIN")
    assert d.plant_id is None
    assert d.device_type is None


def test_device_info_full():
    d = DeviceInfo(
        device_sn="INV001",
        plant_id="plant-1",
        device_type="7",
        family="MIN",
        model="MOD 12KTL3-HU",
        firmware_version="1.0.0",
        status="Normal",
    )
    assert d.family == "MIN"
    assert d.model == "MOD 12KTL3-HU"


# ── PlantSummary / PlantDetail ────────────────────────────────────────────────


def test_plant_summary_optional_fields():
    p = PlantSummary(plant_id="1")
    assert p.plant_name is None
    assert p.total_power is None


def test_plant_detail_empty_devices():
    p = PlantDetail(plant_id="1", plant_name="Home")
    assert p.devices == []


# ── ErrorResponse ─────────────────────────────────────────────────────────────


def test_error_response():
    e = ErrorResponse(error="write_not_permitted", detail="Bridge is in readonly mode.")
    assert e.error == "write_not_permitted"
    assert e.operation is None
