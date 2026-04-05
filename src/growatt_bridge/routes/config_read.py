"""Config read routes.

Endpoints:
- GET /api/v1/devices/{device_sn}/config               — full config snapshot
- GET /api/v1/devices/{device_sn}/config/time-segments — parsed TOU schedule only
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..client import (
    DeviceFamily,
    GrowattClient,
    UnsupportedDeviceFamilyError,
    format_growatt_cloud_error,
)
from ..config import Settings
from ..models import NormalizedConfig, TimeSegment
from .devices import _resolve_plant_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["config"])


# ── Time-segment normalization ─────────────────────────────────────────────────

_HHMM_RE = re.compile(r"^\d{1,2}:\d{1,2}$")


def _to_hhmm(val: Any) -> str | None:
    """Coerce a time value to HH:MM string; returns None on failure."""
    if val is None:
        return None
    s = str(val).strip()
    if _HHMM_RE.match(s):
        # zero-pad the hour if needed
        h, m = s.split(":")
        return f"{int(h):02d}:{int(m):02d}"
    # Some firmware returns minutes-since-midnight integers
    try:
        minutes = int(s)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    except (TypeError, ValueError):
        return s or None


def _parse_segment(raw: dict[str, Any], idx: int) -> TimeSegment | None:
    """Parse a single raw time-segment dict.

    Returns None when the dict does not contain enough usable data.
    """
    seg_num = (
        raw.get("segment")
        or raw.get("segmentNum")
        or raw.get("num")
        or raw.get("index")
        or idx
    )
    try:
        segment = int(seg_num)
        if not (1 <= segment <= 9):
            return None
    except (TypeError, ValueError):
        return None

    mode_raw = raw.get("mode") or raw.get("workMode") or raw.get("batteryMode")
    try:
        mode = int(mode_raw) if mode_raw is not None else 0
    except (TypeError, ValueError):
        mode = 0

    start = _to_hhmm(raw.get("start_time") or raw.get("startTime") or raw.get("startHour"))
    end = _to_hhmm(raw.get("end_time") or raw.get("endTime") or raw.get("endHour"))

    if start is None or end is None:
        return None

    enabled_raw = raw.get("enabled")
    if enabled_raw is None:
        enabled = True
    elif isinstance(enabled_raw, bool):
        enabled = enabled_raw
    else:
        try:
            enabled = bool(int(enabled_raw))
        except (TypeError, ValueError):
            enabled = True

    return TimeSegment(
        segment=segment,
        mode=mode,
        start_time=start,
        end_time=end,
        enabled=enabled,
    )


def _normalize_time_segments(raw_segments: list[dict[str, Any]]) -> list[TimeSegment]:
    result: list[TimeSegment] = []
    for i, raw in enumerate(raw_segments, start=1):
        seg = _parse_segment(raw, i)
        if seg is not None:
            result.append(seg)
    return sorted(result, key=lambda s: s.segment)


# ── Config snapshot normalization ──────────────────────────────────────────────

def _int_or_none(val: Any) -> int | None:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _bool_or_none(val: Any) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    try:
        return bool(int(val))
    except (TypeError, ValueError):
        return None


def _build_config(
    device_sn: str,
    time_segments: list[TimeSegment],
    detail_raw: dict[str, Any] | None = None,
) -> NormalizedConfig:
    """Build a NormalizedConfig.

    Growatt OpenAPI V1 does not expose individual config parameter read
    endpoints for most settings (charge power rate, discharge SOC, etc.).
    These fields are populated from ``detail_raw`` where the API happens
    to include them; they are ``None`` otherwise.

    Use GET /config to see what the bridge can read, and consult
    docs/parameters/ for write semantics.
    """
    raw = detail_raw or {}

    return NormalizedConfig(
        device_sn=device_sn,
        timestamp=datetime.now(timezone.utc),
        # These may be present in some firmware/API versions
        charge_power_rate=_int_or_none(
            raw.get("charge_power")
            or raw.get("pv_active_p_rate")
            or raw.get("pvActivePRate")
            or raw.get("chargePowerRate")
        ),
        discharge_power_rate=_int_or_none(
            raw.get("discharge_power")
            or raw.get("grid_first_discharge_power_rate")
            or raw.get("gridFirstDischargePowerRate")
            or raw.get("dischargePowerRate")
        ),
        discharge_stop_soc=_int_or_none(
            raw.get("on_grid_discharge_stop_soc")
            or raw.get("discharge_stop_soc")
            or raw.get("dischargeStopSoc")
            or raw.get("batteryLowCapacity")
        ),
        ac_charge_enabled=_bool_or_none(
            raw.get("ac_charge") or raw.get("acCharge") or raw.get("acChargeEnable")
        ),
        ac_charge_stop_soc=_int_or_none(
            raw.get("ub_ac_charging_stop_soc")
            or raw.get("ac_charge_soc_limit")
            or raw.get("acChargeSocLimit")
            or raw.get("acChargeStopSoc")
        ),
        export_limit_enabled=_bool_or_none(
            raw.get("export_limit") or raw.get("exportLimit") or raw.get("exportLimitEnable")
        ),
        export_limit_power_rate=_int_or_none(
            raw.get("exportLimitPowerRateStr")
            or raw.get("export_limit_power_rate")
            or raw.get("exportLimitPowerRate")
            or raw.get("exportPowerLimit")
        ),
        time_segments=time_segments,
        raw=raw or None,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get(
    "/api/v1/devices/{device_sn}/config",
    response_model=NormalizedConfig,
    summary="Get device configuration snapshot",
)
async def get_config(
    device_sn: str,
    request: Request,
    plant_id: str | None = Query(
        default=None,
        description="Plant ID containing this device. Defaults to GROWATT_PLANT_ID env var.",
    ),
) -> NormalizedConfig:
    """Return a normalized configuration snapshot for *device_sn*.

    Includes the TOU schedule (time_segments) and any config fields the
    Growatt API makes available for this device/firmware variant.  Most
    numeric config parameters (charge power %, SOC limits, etc.) are
    **write-only** in Growatt OpenAPI V1 and will appear as ``null`` here.
    Use the audit log or GET /config/time-segments for readable config.
    """
    client: GrowattClient = request.app.state.client
    settings: Settings = request.app.state.settings

    resolved_plant_id = await _resolve_plant_id(client, device_sn, settings, hint=plant_id)
    try:
        family = client.detect_device_family(device_sn, resolved_plant_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Growatt Cloud error detecting device family: {format_growatt_cloud_error(exc)}",
        ) from exc

    # Read TOU schedule (MIN only; SPH not yet mapped)
    time_segments: list[TimeSegment] = []
    detail_raw: dict[str, Any] = {}

    if family is DeviceFamily.MIN:
        try:
            raw_segs = client.read_time_segments(device_sn, family)
            time_segments = _normalize_time_segments(raw_segs)
        except UnsupportedDeviceFamilyError:
            pass  # shouldn't happen for MIN, but be defensive
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "read_time_segments(%s) failed: %s",
                device_sn,
                format_growatt_cloud_error(exc),
            )

        # Pull settings bean to extract config fields
        try:
            detail_raw = client.read_device_settings(device_sn, family)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "read_device_settings(%s) for config failed: %s",
                device_sn,
                format_growatt_cloud_error(exc),
            )

    elif family is DeviceFamily.SPH:
        try:
            detail_raw = client.device_detail(device_sn, family)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "device_detail(%s) for config failed: %s",
                device_sn,
                format_growatt_cloud_error(exc),
            )

    else:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported device family {family.value!r} for {device_sn!r}.",
        )

    return _build_config(device_sn, time_segments, detail_raw)


@router.get(
    "/api/v1/devices/{device_sn}/config/time-segments",
    response_model=list[TimeSegment],
    summary="Get TOU time-segment schedule",
)
async def get_time_segments(
    device_sn: str,
    request: Request,
    plant_id: str | None = Query(
        default=None,
        description="Plant ID containing this device. Defaults to GROWATT_PLANT_ID env var.",
    ),
) -> list[TimeSegment]:
    """Return the parsed TOU (Time-of-Use) schedule for *device_sn*.

    Returns up to 9 slots ordered by segment number.  Each slot defines:
    - ``mode``: 0 = load-first, 1 = battery-first, 2 = grid-first
    - ``start_time`` / ``end_time``: HH:MM boundaries
    - ``enabled``: whether this slot is active

    Only supported for MIN/TLX family devices (type 7).
    """
    client: GrowattClient = request.app.state.client
    settings: Settings = request.app.state.settings

    resolved_plant_id = await _resolve_plant_id(client, device_sn, settings, hint=plant_id)
    try:
        family = client.detect_device_family(device_sn, resolved_plant_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Growatt Cloud error detecting device family: {format_growatt_cloud_error(exc)}",
        ) from exc

    if family is not DeviceFamily.MIN:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Time-segment schedule is only supported for MIN/TLX devices "
                f"(detected family: {family.value!r})."
            ),
        )

    try:
        raw_segs = client.read_time_segments(device_sn, family)
    except UnsupportedDeviceFamilyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        detail = format_growatt_cloud_error(exc)
        logger.error("read_time_segments(%s) failed: %s", device_sn, detail)
        raise HTTPException(status_code=502, detail=f"Growatt Cloud error: {detail}") from exc

    return _normalize_time_segments(raw_segs)
