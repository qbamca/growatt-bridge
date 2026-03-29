"""Tests for growatt_bridge.config (Settings parsing and helpers)."""

from __future__ import annotations

import pytest

from growatt_bridge.config import VALID_WRITE_OPERATIONS, Settings
from tests.conftest import make_settings


# ── Default values ────────────────────────────────────────────────────────────


def test_defaults():
    s = make_settings()
    assert s.growatt_server_url == "https://openapi.growatt.com/"
    assert s.bridge_port == 8081
    assert s.bridge_host == "0.0.0.0"
    assert s.bridge_readonly is True
    assert s.bridge_write_allowlist == ""
    assert s.bridge_rate_limit_writes == 3
    assert s.bridge_require_readback is True


def test_token_stored():
    s = make_settings(growatt_api_token="my-secret-token")
    assert s.growatt_api_token == "my-secret-token"


# ── URL normalisation ─────────────────────────────────────────────────────────


def test_server_url_trailing_slash_added():
    s = make_settings(growatt_server_url="https://openapi.growatt.com")
    assert s.growatt_server_url == "https://openapi.growatt.com/"


def test_server_url_trailing_slash_preserved():
    s = make_settings(growatt_server_url="https://openapi.growatt.com/")
    assert s.growatt_server_url == "https://openapi.growatt.com/"


# ── Token redaction ───────────────────────────────────────────────────────────


def test_redacted_token_long():
    s = make_settings(growatt_api_token="abcdefghijklmn")
    redacted = s.redacted_token()
    assert "abcdefghijklmn" not in redacted
    assert redacted.startswith("abcd")
    assert redacted.endswith("lmn")
    assert "***" in redacted


def test_redacted_token_short():
    s = make_settings(growatt_api_token="ab")
    assert s.redacted_token() == "***"


def test_redacted_token_exactly_8():
    s = make_settings(growatt_api_token="12345678")
    assert s.redacted_token() == "***"


# ── parsed_write_allowlist ────────────────────────────────────────────────────


def test_empty_allowlist_returns_empty_list():
    s = make_settings(bridge_write_allowlist="")
    assert s.parsed_write_allowlist() == []


def test_single_valid_operation():
    s = make_settings(bridge_write_allowlist="set_charge_power")
    assert s.parsed_write_allowlist() == ["set_charge_power"]


def test_multiple_valid_operations():
    s = make_settings(bridge_write_allowlist="set_charge_power,set_discharge_power")
    assert set(s.parsed_write_allowlist()) == {"set_charge_power", "set_discharge_power"}


def test_allowlist_strips_whitespace():
    s = make_settings(bridge_write_allowlist=" set_charge_power , set_discharge_power ")
    assert set(s.parsed_write_allowlist()) == {"set_charge_power", "set_discharge_power"}


def test_invalid_operation_raises():
    s = make_settings(bridge_write_allowlist="set_charge_power,totally_fake_op")
    with pytest.raises(ValueError, match="totally_fake_op"):
        s.parsed_write_allowlist()


def test_all_valid_operations_accepted():
    allowlist = ",".join(VALID_WRITE_OPERATIONS)
    s = make_settings(bridge_write_allowlist=allowlist)
    result = set(s.parsed_write_allowlist())
    assert result == VALID_WRITE_OPERATIONS


# ── is_operation_allowed ──────────────────────────────────────────────────────


def test_readonly_blocks_all_operations():
    s = make_settings(
        bridge_readonly=True,
        bridge_write_allowlist="set_charge_power",
    )
    assert s.is_operation_allowed("set_charge_power") is False


def test_write_mode_unlists_operation():
    s = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_charge_power",
    )
    assert s.is_operation_allowed("set_charge_power") is True


def test_write_mode_blocks_non_allowlisted_operation():
    s = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="set_charge_power",
    )
    assert s.is_operation_allowed("set_discharge_power") is False


def test_invalid_allowlist_returns_false_not_raises():
    s = make_settings(
        bridge_readonly=False,
        bridge_write_allowlist="fake_op",
    )
    # is_operation_allowed must never raise; it returns False on bad allowlist
    assert s.is_operation_allowed("fake_op") is False
