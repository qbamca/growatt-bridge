"""GET /api/v1/devices/{device_sn}/telemetry — normalized live telemetry."""

from __future__ import annotations

import logging
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
from ..models import NormalizedTelemetry
from .devices import _resolve_plant_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telemetry"])


# ── Field-mapping helpers ──────────────────────────────────────────────────────


def _get(raw: dict[str, Any], *keys: str) -> Any:
    """Return the first non-None value matching any of *keys* in *raw*."""
    for k in keys:
        v = raw.get(k)
        if v is not None:
            return v
    return None


def _float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return False


# ── Normalization ──────────────────────────────────────────────────────────────

# Status code → human-readable text mapping (subset of known Growatt codes)
_STATUS_MAP: dict[int, str] = {
    0: "Standby",
    1: "Normal",
    2: "Fault",
    3: "Flash",
    4: "PV charging",
    5: "AC charging",
    6: "Combined charging",
    7: "Combined charge and bypass",
    8: "PV charging and bypass",
    9: "AC charging and bypass",
    10: "Bypass",
    11: "PV charge and AC charge and bypass",
}


def normalize_min_telemetry(device_sn: str, raw: dict[str, Any]) -> NormalizedTelemetry:
    """Map a growattServer MIN/TLX detail response to NormalizedTelemetry.

    growattServer field names are camelCase; we try multiple aliases to
    handle minor differences across library versions and firmware variants.
    """
    status_raw = _int(_get(raw, "status", "statusValue", "deviceStatus"))
    status_text = _STATUS_MAP.get(status_raw, str(status_raw)) if status_raw is not None else None

    return NormalizedTelemetry(
        device_sn=device_sn,
        timestamp=datetime.now(timezone.utc),
        # PV input
        ppv=_float(_get(raw, "ppv", "totalPpv")),
        vpv1=_float(_get(raw, "vpv1")),
        vpv2=_float(_get(raw, "vpv2")),
        ipv1=_float(_get(raw, "ipv1")),
        ipv2=_float(_get(raw, "ipv2")),
        # AC output
        pac=_float(_get(raw, "pac", "totalActivePower")),
        vac1=_float(_get(raw, "vac1")),
        vac2=_float(_get(raw, "vac2")),
        vac3=_float(_get(raw, "vac3")),
        iac1=_float(_get(raw, "iac1")),
        iac2=_float(_get(raw, "iac2")),
        iac3=_float(_get(raw, "iac3")),
        fac=_float(_get(raw, "fac", "frequency")),
        # Battery
        soc=_float(_get(raw, "soc", "batterySOC", "bdc1_SOC")),
        p_charge=_float(_get(raw, "pCharge", "p_charge", "chargePower", "bdc1_chargePower")),
        p_discharge=_float(
            _get(raw, "pDisCharge", "pDischarge", "p_discharge", "dischargePower")
        ),
        v_bat=_float(_get(raw, "vBattery1", "vBattery", "v_bat", "batteryVoltage")),
        i_bat=_float(_get(raw, "iBattery1", "iBattery", "i_bat", "batteryCurrent")),
        # Grid
        p_to_grid=_float(_get(raw, "pToGrid", "p_to_grid", "exportPower")),
        p_to_user=_float(_get(raw, "pToUser", "p_to_user", "importPower")),
        # Energy counters
        e_today=_float(_get(raw, "eday", "eDay", "ePvToday", "energyToday")),
        e_total=_float(_get(raw, "etotal", "eTotal", "ePvTotal", "energyTotal")),
        e_charge_today=_float(
            _get(raw, "eBatChargeToday", "eBatCharge_day", "chargeEnergyToday")
        ),
        e_discharge_today=_float(
            _get(raw, "eBatDischargeToday", "eBatDisCharge_day", "dischargeEnergyToday")
        ),
        e_to_grid_today=_float(
            _get(raw, "eToGridToday", "eToGrid_day", "exportEnergyToday")
        ),
        e_from_grid_today=_float(
            _get(raw, "eFromGridToday", "eLocalLoad_day", "importEnergyToday")
        ),
        # Temperature
        temp1=_float(_get(raw, "temperature", "temperature1", "temp1", "inverterTemperature")),
        temp2=_float(_get(raw, "temperature2", "temp2")),
        # Status
        status_code=status_raw,
        status_text=status_text,
        lost=_bool(_get(raw, "lost", "isLost", "deviceLost")),
        raw=raw,
    )


# ── Route ──────────────────────────────────────────────────────────────────────


@router.get(
    "/api/v1/devices/{device_sn}/telemetry",
    response_model=NormalizedTelemetry,
    summary="Get live telemetry",
)
async def get_telemetry(
    device_sn: str,
    request: Request,
    plant_id: str | None = Query(
        default=None,
        description="Plant ID containing this device. Defaults to GROWATT_PLANT_ID env var.",
    ),
) -> NormalizedTelemetry:
    """Return a normalized live telemetry snapshot for *device_sn*.

    Normalizes PV power, AC output, battery, grid, energy counters, and
    temperatures into consistent snake_case fields with documented units.
    """
    client: GrowattClient = request.app.state.client
    settings: Settings = request.app.state.settings

    resolved_plant_id = await _resolve_plant_id(client, device_sn, settings, hint=plant_id)
    family = client.detect_device_family(device_sn, resolved_plant_id)

    try:
        raw = client.device_detail(device_sn, family)
    except UnsupportedDeviceFamilyError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        detail = format_growatt_cloud_error(exc)
        logger.error("device_detail(%s) for telemetry failed: %s", device_sn, detail)
        raise HTTPException(status_code=502, detail=f"Growatt Cloud error: {detail}") from exc

    if family is DeviceFamily.MIN:
        return normalize_min_telemetry(device_sn, raw)

    # SPH: best-effort, same field mapping (many fields overlap)
    return normalize_min_telemetry(device_sn, raw)
