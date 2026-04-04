"""Integration tests for write operations.

Each test follows the mandatory cycle:
  1. Read current value from the inverter
  2. Write a safely-mutated value
  3. Assert success
  4. Re-read and assert the value changed as expected
  5. Restore the original value (in a try/finally so restore always runs)
  6. Re-read and assert the value is back to the original

Tests use segment 9 for TOU writes — the highest-numbered slot, which is
typically disabled and safe to disturb.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.integration

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_config(client: AsyncClient, sn: str) -> dict:
    r = await client.get(f"/api/v1/devices/{sn}/config")
    assert r.status_code == 200, f"GET /config failed: {r.text}"
    return r.json()


async def _get_time_segments(client: AsyncClient, sn: str) -> list[dict]:
    r = await client.get(f"/api/v1/devices/{sn}/config/time-segments")
    assert r.status_code == 200, f"GET /config/time-segments failed: {r.text}"
    return r.json()


async def _write(
    client: AsyncClient,
    sn: str,
    operation_id: str,
    params: dict,
) -> dict:
    r = await client.post(
        f"/api/v1/devices/{sn}/commands/{operation_id}",
        json={"params": params},
    )
    assert r.status_code == 200, f"POST {operation_id} returned {r.status_code}: {r.text}"
    return r.json()


def _find_segment(segments: list[dict], num: int) -> dict | None:
    for s in segments:
        if s.get("segment") == num:
            return s
    return None


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_set_ac_charge_stop_soc(
    live_app_client: AsyncClient, device_sn: str
) -> None:
    """Write a new AC charge stop SOC, verify it changed, then restore."""
    config = await _get_config(live_app_client, device_sn)
    original = config.get("ac_charge_stop_soc")
    if original is None:
        pytest.skip("ac_charge_stop_soc not readable on this device/firmware")

    # Compute a safe adjacent value (stays in 10–100)
    new_val = original - 5 if original >= 15 else original + 5

    try:
        result = await _write(
            live_app_client, device_sn, "set_ac_charge_stop_soc", {"value": new_val}
        )
        assert result["success"], f"write failed: {result.get('error')}"

        # Verify change
        after = (await _get_config(live_app_client, device_sn)).get("ac_charge_stop_soc")
        assert after == new_val, f"expected ac_charge_stop_soc={new_val}, got {after}"

    finally:
        # Always restore
        restore = await _write(
            live_app_client, device_sn, "set_ac_charge_stop_soc", {"value": original}
        )
        assert restore["success"], f"restore failed: {restore.get('error')}"

        restored = (await _get_config(live_app_client, device_sn)).get("ac_charge_stop_soc")
        assert restored == original, (
            f"restore failed: expected ac_charge_stop_soc={original}, got {restored}"
        )


async def test_set_on_grid_discharge_stop_soc(
    live_app_client: AsyncClient, device_sn: str
) -> None:
    """Write a new on-grid discharge stop SOC, verify it changed, then restore."""
    config = await _get_config(live_app_client, device_sn)
    original = config.get("discharge_stop_soc")
    if original is None:
        pytest.skip("discharge_stop_soc not readable on this device/firmware")

    # Compute a safe adjacent value (stays in 10–100)
    new_val = original - 5 if original >= 15 else original + 5

    try:
        result = await _write(
            live_app_client, device_sn, "set_on_grid_discharge_stop_soc", {"value": new_val}
        )
        assert result["success"], f"write failed: {result.get('error')}"

        # Verify change
        after = (await _get_config(live_app_client, device_sn)).get("discharge_stop_soc")
        assert after == new_val, f"expected discharge_stop_soc={new_val}, got {after}"

    finally:
        # Always restore
        restore = await _write(
            live_app_client, device_sn, "set_on_grid_discharge_stop_soc", {"value": original}
        )
        assert restore["success"], f"restore failed: {restore.get('error')}"

        restored = (await _get_config(live_app_client, device_sn)).get("discharge_stop_soc")
        assert restored == original, (
            f"restore failed: expected discharge_stop_soc={original}, got {restored}"
        )


async def test_set_ac_charge_enable(
    live_app_client: AsyncClient, device_sn: str
) -> None:
    """Toggle AC charge enable, verify it changed, then restore."""
    config = await _get_config(live_app_client, device_sn)
    original = config.get("ac_charge_enabled")
    if original is None:
        pytest.skip("ac_charge_enabled not readable on this device/firmware")

    new_val = not original

    try:
        result = await _write(
            live_app_client, device_sn, "set_ac_charge_enable", {"enabled": new_val}
        )
        assert result["success"], f"write failed: {result.get('error')}"

        # Verify change
        after = (await _get_config(live_app_client, device_sn)).get("ac_charge_enabled")
        assert after == new_val, f"expected ac_charge_enabled={new_val}, got {after}"

    finally:
        # Always restore
        restore = await _write(
            live_app_client, device_sn, "set_ac_charge_enable", {"enabled": original}
        )
        assert restore["success"], f"restore failed: {restore.get('error')}"

        restored = (await _get_config(live_app_client, device_sn)).get("ac_charge_enabled")
        assert restored == original, (
            f"restore failed: expected ac_charge_enabled={original}, got {restored}"
        )


async def test_set_time_segment(
    live_app_client: AsyncClient, device_sn: str
) -> None:
    """Write TOU segment 9, verify it changed, then restore.

    Segment 9 is chosen because it is typically disabled and the last slot,
    making it the safest to modify during testing.
    """
    _SEGMENT = 9

    segments = await _get_time_segments(live_app_client, device_sn)
    existing = _find_segment(segments, _SEGMENT)

    # Use the existing segment state as the original, or safe defaults if absent.
    if existing:
        orig_mode = existing["mode"]
        orig_start = existing["start_time"]
        orig_end = existing["end_time"]
        orig_enabled = existing["enabled"]
    else:
        orig_mode = 0
        orig_start = "00:00"
        orig_end = "00:00"
        orig_enabled = False

    # Safely mutate the mode (cycle 0→1→2→0) while keeping everything else.
    new_mode = (orig_mode + 1) % 3
    new_params = {
        "segment": _SEGMENT,
        "mode": new_mode,
        "start_time": orig_start,
        "end_time": orig_end,
        "enabled": orig_enabled,
    }
    orig_params = {
        "segment": _SEGMENT,
        "mode": orig_mode,
        "start_time": orig_start,
        "end_time": orig_end,
        "enabled": orig_enabled,
    }

    try:
        result = await _write(
            live_app_client, device_sn, "set_time_segment", new_params
        )
        assert result["success"], f"write failed: {result.get('error')}"

        # Verify change via explicit re-read
        after_segments = await _get_time_segments(live_app_client, device_sn)
        after_seg = _find_segment(after_segments, _SEGMENT)
        assert after_seg is not None, f"segment {_SEGMENT} not found after write"
        assert after_seg["mode"] == new_mode, (
            f"expected mode={new_mode}, got {after_seg['mode']}"
        )

        # Additionally verify via the in-response readback (available for time segments)
        readback = result.get("readback")
        if readback and not readback.get("readback_failed"):
            assert "mode" not in readback.get("changed", {}), (
                "readback shows mode unchanged but we expected a change"
            )

    finally:
        # Always restore
        restore = await _write(
            live_app_client, device_sn, "set_time_segment", orig_params
        )
        assert restore["success"], f"restore failed: {restore.get('error')}"

        restored_segments = await _get_time_segments(live_app_client, device_sn)
        restored_seg = _find_segment(restored_segments, _SEGMENT)
        assert restored_seg is not None, f"segment {_SEGMENT} not found after restore"
        assert restored_seg["mode"] == orig_mode, (
            f"restore failed: expected mode={orig_mode}, got {restored_seg['mode']}"
        )
