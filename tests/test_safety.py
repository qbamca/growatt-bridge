"""Tests for growatt_bridge.safety (SafetyLayer, validators, rate limiter, audit)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from growatt_bridge.client import DeviceFamily
from growatt_bridge.safety import (
    OPERATION_REGISTRY,
    OperationValidationError,
    RateLimitError,
    SafetyLayer,
    UnknownOperationError,
    WriteNotPermittedError,
    _SlidingWindowRateLimiter,
    _AuditLogger,
    _is_api_success,
    _extract_api_error,
    _is_valid_hhmm,
    _validate_time_segment_params,
    _validate_parameter_params,
)
from tests.conftest import make_mock_client, make_settings


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_layer(
    tmp_path: Path,
    allowlist: str = "set_charge_power",
    readonly: bool = False,
    rate_limit: int = 10,
) -> SafetyLayer:
    """Return a SafetyLayer configured for writes with a temp audit log."""
    settings = make_settings(
        bridge_readonly=readonly,
        bridge_write_allowlist=allowlist,
        bridge_rate_limit_writes=rate_limit,
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    client = make_mock_client()
    client.min_write_parameter.return_value = {"result_code": "1"}
    return SafetyLayer(settings, client)


# ── check_write_permitted ─────────────────────────────────────────────────────


def test_readonly_blocks_write(tmp_path):
    layer = _write_layer(tmp_path, readonly=True)
    with pytest.raises(WriteNotPermittedError, match="readonly mode"):
        layer.check_write_permitted("set_charge_power")


def test_unknown_operation_raises(tmp_path):
    layer = _write_layer(tmp_path)
    with pytest.raises(UnknownOperationError, match="unknown_op"):
        layer.check_write_permitted("unknown_op")


def test_not_allowlisted_raises(tmp_path):
    layer = _write_layer(tmp_path, allowlist="set_discharge_power")
    with pytest.raises(WriteNotPermittedError, match="not in BRIDGE_WRITE_ALLOWLIST"):
        layer.check_write_permitted("set_charge_power")


def test_allowlisted_operation_passes(tmp_path):
    layer = _write_layer(tmp_path)
    # Should not raise
    layer.check_write_permitted("set_charge_power")


# ── validate_params ───────────────────────────────────────────────────────────


def test_validate_unknown_op(tmp_path):
    layer = _write_layer(tmp_path)
    with pytest.raises(UnknownOperationError):
        layer.validate_params("not_real", {})


def test_set_charge_power_valid(tmp_path):
    layer = _write_layer(tmp_path)
    errors = layer.validate_params("set_charge_power", {"value": 75})
    assert errors == []


def test_set_charge_power_above_max(tmp_path):
    layer = _write_layer(tmp_path)
    errors = layer.validate_params("set_charge_power", {"value": 101})
    assert any("≤ 100" in e for e in errors)


def test_set_charge_power_below_min(tmp_path):
    layer = _write_layer(tmp_path)
    errors = layer.validate_params("set_charge_power", {"value": -1})
    assert any("≥ 0" in e for e in errors)


def test_set_charge_power_missing_value(tmp_path):
    layer = _write_layer(tmp_path)
    errors = layer.validate_params("set_charge_power", {})
    assert any("required" in e for e in errors)


def test_set_discharge_stop_soc_floor(tmp_path):
    layer = _write_layer(tmp_path, allowlist="set_discharge_stop_soc")
    # 0 must be rejected — hardcoded hardware floor of 10
    errors = layer.validate_params("set_discharge_stop_soc", {"value": 0})
    assert any("≥ 10" in e for e in errors)


def test_set_discharge_stop_soc_boundary(tmp_path):
    layer = _write_layer(tmp_path, allowlist="set_discharge_stop_soc")
    assert layer.validate_params("set_discharge_stop_soc", {"value": 10}) == []
    assert layer.validate_params("set_discharge_stop_soc", {"value": 100}) == []


def test_set_ac_charge_enable_valid_bool(tmp_path):
    layer = _write_layer(tmp_path, allowlist="set_ac_charge_enable")
    assert layer.validate_params("set_ac_charge_enable", {"enabled": True}) == []
    assert layer.validate_params("set_ac_charge_enable", {"enabled": False}) == []


def test_set_ac_charge_enable_rejects_non_bool(tmp_path):
    layer = _write_layer(tmp_path, allowlist="set_ac_charge_enable")
    errors = layer.validate_params("set_ac_charge_enable", {"enabled": 1})
    assert any("boolean" in e for e in errors)


def test_set_export_limit_requires_meter_acknowledged(tmp_path):
    layer = _write_layer(tmp_path, allowlist="set_export_limit")
    errors = layer.validate_params("set_export_limit", {"value": 50})
    assert any("meter_acknowledged" in e for e in errors)


def test_set_export_limit_with_meter_acknowledged(tmp_path):
    layer = _write_layer(tmp_path, allowlist="set_export_limit")
    errors = layer.validate_params("set_export_limit", {"value": 50, "meter_acknowledged": True})
    assert errors == []


# ── set_time_segment params ───────────────────────────────────────────────────


def test_time_segment_valid():
    errors = _validate_time_segment_params(
        {"segment": 1, "mode": 0, "start_time": "08:00", "end_time": "20:00"}
    )
    assert errors == []


def test_time_segment_out_of_range():
    errors = _validate_time_segment_params(
        {"segment": 10, "mode": 0, "start_time": "08:00", "end_time": "20:00"}
    )
    assert any("1–9" in e for e in errors)


def test_time_segment_bad_mode():
    errors = _validate_time_segment_params(
        {"segment": 1, "mode": 5, "start_time": "08:00", "end_time": "20:00"}
    )
    assert any("0, 1, or 2" in e for e in errors)


def test_time_segment_invalid_time_format():
    errors = _validate_time_segment_params(
        {"segment": 1, "mode": 0, "start_time": "8am", "end_time": "20:00"}
    )
    assert any("HH:MM" in e for e in errors)


def test_time_segment_missing_fields():
    errors = _validate_time_segment_params({})
    assert len(errors) == 4  # segment, mode, start_time, end_time all missing


# ── _is_valid_hhmm ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("00:00", True),
        ("23:59", True),
        ("08:30", True),
        ("24:00", False),
        ("23:60", False),
        ("8:30", True),  # Single-digit hour is fine
        ("abc", False),
        ("", False),
        ("12", False),
    ],
)
def test_is_valid_hhmm(value: str, expected: bool):
    assert _is_valid_hhmm(value) is expected


# ── _is_api_success / _extract_api_error ──────────────────────────────────────


@pytest.mark.parametrize(
    "response,expected",
    [
        ({"result_code": "1"}, True),
        ({"resultCode": "1"}, True),
        ({"result": 1}, True),
        ({"result": "success"}, True),
        ({"result": True}, True),
        ({"success": True}, True),
        ({"success": False}, False),
        ({"success": True, "result_code": "0"}, True),
        ({"result_code": "0"}, False),
        ({"result_code": "2"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_is_api_success(response, expected: bool):
    assert _is_api_success(response) is expected


def test_extract_api_error_result_msg():
    assert "bad token" in _extract_api_error({"result_code": "0", "result_msg": "bad token"})


def test_extract_api_error_empty():
    assert "Empty" in _extract_api_error(None)


def test_extract_api_error_code_fallback():
    msg = _extract_api_error({"result_code": "403"})
    assert "403" in msg


# ── _SlidingWindowRateLimiter ─────────────────────────────────────────────────


def test_rate_limiter_allows_up_to_max():
    limiter = _SlidingWindowRateLimiter(max_calls=3, window_seconds=60)
    assert limiter.check_and_record() is True
    assert limiter.check_and_record() is True
    assert limiter.check_and_record() is True
    assert limiter.check_and_record() is False  # 4th within window


def test_rate_limiter_current_count():
    limiter = _SlidingWindowRateLimiter(max_calls=5, window_seconds=60)
    assert limiter.current_count == 0
    limiter.check_and_record()
    limiter.check_and_record()
    assert limiter.current_count == 2


# ── _AuditLogger ──────────────────────────────────────────────────────────────


def test_audit_logger_writes_entry(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit = _AuditLogger(log_path)
    audit_id = audit.record({"operation": "set_charge_power", "device_sn": "INV001"})

    assert log_path.exists()
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["operation"] == "set_charge_power"
    assert entry["audit_id"] == audit_id
    assert "logged_at" in entry


def test_audit_logger_redacts_token(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit = _AuditLogger(log_path)
    audit.record({"token": "supersecret", "api_token": "also-secret", "operation": "op"})

    content = log_path.read_text()
    assert "supersecret" not in content
    assert "also-secret" not in content


def test_audit_logger_multiple_entries(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit = _AuditLogger(log_path)
    audit.record({"operation": "op1"})
    audit.record({"operation": "op2"})

    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["operation"] == "op1"
    assert json.loads(lines[1])["operation"] == "op2"


def test_audit_logger_survives_bad_path(caplog):
    """Audit log failure must not raise — it logs a warning only."""
    audit = _AuditLogger(Path("/proc/readonly-does-not-exist/audit.jsonl"))
    # Should return an audit_id without raising
    audit_id = audit.record({"operation": "op"})
    assert audit_id  # UUID returned even on I/O failure


# ── SafetyLayer.execute_write ─────────────────────────────────────────────────


def test_execute_write_readonly_raises(tmp_path):
    settings = make_settings(
        bridge_readonly=True,
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    client = make_mock_client()
    layer = SafetyLayer(settings, client)
    with pytest.raises(WriteNotPermittedError):
        layer.execute_write("set_charge_power", "INV001", DeviceFamily.MIN, {"value": 50})


def test_execute_write_unsupported_family_raises(tmp_path):
    layer = _write_layer(tmp_path)
    with pytest.raises(Exception):
        # set_charge_power only supports MIN; SPH should raise
        layer.execute_write("set_charge_power", "INV001", DeviceFamily.SPH, {"value": 50})


def test_execute_write_validation_error_raises(tmp_path):
    layer = _write_layer(tmp_path)
    with pytest.raises(OperationValidationError):
        layer.execute_write("set_charge_power", "INV001", DeviceFamily.MIN, {"value": 999})


def test_execute_write_rate_limit_raises(tmp_path):
    layer = _write_layer(tmp_path, rate_limit=1)
    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_charge_power",
        bridge_rate_limit_writes=1,
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    client = make_mock_client()
    client.min_write_parameter.return_value = {"result_code": "1"}
    layer2 = SafetyLayer(settings, client)

    layer2.execute_write("set_charge_power", "INV001", DeviceFamily.MIN, {"value": 50})
    with pytest.raises(RateLimitError):
        layer2.execute_write("set_charge_power", "INV001", DeviceFamily.MIN, {"value": 60})


def test_execute_write_success_returns_command_response(tmp_path):
    layer = _write_layer(tmp_path)
    resp = layer.execute_write("set_charge_power", "INV001", DeviceFamily.MIN, {"value": 75})
    assert resp.operation == "set_charge_power"
    assert resp.device_sn == "INV001"
    assert resp.audit_id
    assert resp.success is True


def test_execute_write_api_failure_captured_in_response(tmp_path):
    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_charge_power",
        bridge_rate_limit_writes=10,
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    client = make_mock_client()
    client.min_write_parameter.return_value = {"result_code": "0", "result_msg": "invalid token"}
    layer = SafetyLayer(settings, client)

    resp = layer.execute_write("set_charge_power", "INV001", DeviceFamily.MIN, {"value": 50})
    assert resp.success is False
    assert "invalid token" in (resp.error or "")


# ── SafetyLayer.dry_run_validate ──────────────────────────────────────────────


def test_dry_run_valid(tmp_path):
    layer = _write_layer(tmp_path)
    valid, errors = layer.dry_run_validate(
        "set_charge_power", "INV001", DeviceFamily.MIN, {"value": 50}
    )
    assert valid is True
    assert errors == []


def test_dry_run_invalid_params(tmp_path):
    layer = _write_layer(tmp_path)
    valid, errors = layer.dry_run_validate(
        "set_charge_power", "INV001", DeviceFamily.MIN, {"value": 200}
    )
    assert valid is False
    assert errors


def test_dry_run_readonly_returns_error(tmp_path):
    settings = make_settings(
        bridge_readonly=True,
        bridge_write_allowlist="set_charge_power",
        bridge_audit_log=tmp_path / "audit.jsonl",
    )
    client = make_mock_client()
    layer = SafetyLayer(settings, client)
    valid, errors = layer.dry_run_validate(
        "set_charge_power", "INV001", DeviceFamily.MIN, {"value": 50}
    )
    assert valid is False
    assert any("readonly" in e.lower() for e in errors)


# ── Legacy web MIN writes ─────────────────────────────────────────────────────


def test_legacy_prereq_missing_plant_id(tmp_path):
    settings = make_settings(
        bridge_audit_log=tmp_path / "audit.jsonl",
        bridge_legacy_web_min_writes=True,
        growatt_web_username="u",
        growatt_web_password="p",
    )
    layer = SafetyLayer(settings, make_mock_client())
    errors = layer.validate_params(
        "set_charge_power",
        {"value": 50},
        plant_id=None,
        family=DeviceFamily.MIN,
    )
    assert any("plant ID" in e for e in errors)


def test_legacy_prereq_missing_web_password(tmp_path):
    settings = make_settings(
        bridge_audit_log=tmp_path / "audit.jsonl",
        bridge_legacy_web_min_writes=True,
        growatt_web_username="u",
        growatt_web_password=None,
    )
    layer = SafetyLayer(settings, make_mock_client())
    errors = layer.validate_params(
        "set_charge_power",
        {"value": 50},
        plant_id="plant-1",
        family=DeviceFamily.MIN,
    )
    assert any("GROWATT_WEB" in e for e in errors)


def test_legacy_prereq_skipped_for_sph(tmp_path):
    settings = make_settings(
        bridge_audit_log=tmp_path / "audit.jsonl",
        bridge_legacy_web_min_writes=True,
    )
    layer = SafetyLayer(settings, make_mock_client())
    errors = layer.validate_params(
        "set_charge_power",
        {"value": 50},
        plant_id=None,
        family=DeviceFamily.SPH,
    )
    assert not any("Legacy web" in e for e in errors)


def test_legacy_execute_uses_tcp_set_scalar(tmp_path):
    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_charge_power",
        bridge_rate_limit_writes=10,
        bridge_audit_log=tmp_path / "audit.jsonl",
        bridge_legacy_web_min_writes=True,
        growatt_web_username="u",
        growatt_web_password="p",
    )
    client = make_mock_client()
    layer = SafetyLayer(settings, client)
    mock_legacy = MagicMock()
    mock_legacy.tcp_set_scalar.return_value = {"success": True}

    with patch.object(layer, "_get_legacy_client", return_value=mock_legacy):
        resp = layer.execute_write(
            "set_charge_power",
            "INV001",
            DeviceFamily.MIN,
            {"value": 50},
            plant_id="plant-1",
        )

    assert resp.success is True
    mock_legacy.tcp_set_scalar.assert_called_once_with(
        "plant-1", "INV001", "charge_power_command", "50"
    )
    client.min_write_parameter.assert_not_called()


def test_legacy_time_segment_uses_tcp_set(tmp_path):
    settings = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_time_segment",
        bridge_rate_limit_writes=10,
        bridge_audit_log=tmp_path / "audit.jsonl",
        bridge_legacy_web_min_writes=True,
        growatt_web_username="u",
        growatt_web_password="p",
    )
    client = make_mock_client()
    layer = SafetyLayer(settings, client)
    mock_legacy = MagicMock()
    mock_legacy.tcp_set_time_segment.return_value = {"success": True}

    params = {
        "segment": 2,
        "mode": 1,
        "start_time": "08:30",
        "end_time": "17:00",
        "enabled": True,
    }
    with patch.object(layer, "_get_legacy_client", return_value=mock_legacy):
        resp = layer.execute_write(
            "set_time_segment",
            "INV001",
            DeviceFamily.MIN,
            params,
            plant_id="plant-9",
        )

    assert resp.success is True
    mock_legacy.tcp_set_time_segment.assert_called_once_with(
        "plant-9", "INV001", 2, 1, 8, 30, 17, 0, True
    )
    client.min_write_time_segment.assert_not_called()
