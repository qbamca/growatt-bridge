"""Device read routes.

Endpoints:
- GET /api/v1/plants/{plant_id}/devices      — list devices in a plant
- GET /api/v1/devices/{device_sn}            — device detail (family-routed)
- GET /api/v1/devices/{device_sn}/capabilities
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..client import DeviceFamily, GrowattClient, UnsupportedDeviceFamilyError
from ..config import Settings
from ..models import DeviceCapabilities, DeviceInfo
from ..safety import OPERATION_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter(tags=["devices"])

# ── Supported read operations per family ──────────────────────────────────────

_MIN_READ_OPS = [
    "telemetry",
    "config",
    "config/time-segments",
    "capabilities",
]

_SPH_READ_OPS = [
    "telemetry",
    "capabilities",
]


# ── Normalization helpers ──────────────────────────────────────────────────────


def _sn_from_raw(dev: dict[str, Any]) -> str:
    return str(
        dev.get("device_sn")
        or dev.get("deviceSn")
        or dev.get("serialNum")
        or dev.get("sn")
        or ""
    )


def _normalize_device_info(raw: dict[str, Any], family: DeviceFamily) -> DeviceInfo:
    return DeviceInfo(
        device_sn=_sn_from_raw(raw),
        plant_id=str(raw.get("plant_id") or raw.get("plantId") or "")
        or None,
        device_type=str(raw.get("deviceType") or raw.get("type") or raw.get("device_type") or "")
        or None,
        family=family.value,
        model=raw.get("deviceModel") or raw.get("model") or raw.get("deviceAlias"),
        firmware_version=raw.get("firmwareVersion") or raw.get("firmware"),
        status=str(raw.get("status")) if raw.get("status") is not None else None,
    )


# ── Shared helper: resolve plant_id for a device SN ──────────────────────────


async def _resolve_plant_id(
    client: GrowattClient,
    device_sn: str,
    settings: Settings,
    hint: str | None = None,
) -> str:
    """Return the plant_id that contains *device_sn*.

    Resolution order:
    1. URL/query ``hint`` (if provided)
    2. ``settings.growatt_plant_id``
    3. Scan all plants (first match wins)

    Raises ``HTTPException(404)`` when the device is not found anywhere.
    """
    if hint:
        return hint
    if settings.growatt_plant_id:
        return settings.growatt_plant_id

    # Scan all plants
    try:
        plants = client.plant_list()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Growatt Cloud error: {exc}") from exc

    for plant in plants:
        plant_id = str(
            plant.get("plant_id") or plant.get("plantId") or plant.get("id") or ""
        )
        if not plant_id:
            continue
        try:
            devices = client.device_list(plant_id)
        except Exception:  # noqa: BLE001
            continue
        for dev in devices:
            if _sn_from_raw(dev) == device_sn:
                return plant_id

    raise HTTPException(
        status_code=404,
        detail=f"Device {device_sn!r} not found in any plant.",
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get(
    "/api/v1/plants/{plant_id}/devices",
    response_model=list[DeviceInfo],
    summary="List devices in a plant",
)
async def list_plant_devices(plant_id: str, request: Request) -> list[DeviceInfo]:
    """Return all devices registered under *plant_id*."""
    client: GrowattClient = request.app.state.client
    try:
        devices = client.device_list(plant_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("device_list(%s) failed: %s", plant_id, exc)
        raise HTTPException(status_code=502, detail=f"Growatt Cloud error: {exc}") from exc

    result: list[DeviceInfo] = []
    for dev in devices:
        sn = _sn_from_raw(dev)
        family = (
            client.detect_device_family(sn, plant_id)
            if sn
            else DeviceFamily.UNKNOWN
        )
        info = _normalize_device_info(dev, family)
        if not info.plant_id:
            info = info.model_copy(update={"plant_id": plant_id})
        result.append(info)
    return result


@router.get(
    "/api/v1/devices/{device_sn}",
    response_model=DeviceInfo,
    summary="Get device detail",
)
async def get_device(
    device_sn: str,
    request: Request,
    plant_id: str | None = Query(
        default=None,
        description="Plant ID containing this device. Defaults to GROWATT_PLANT_ID env var.",
    ),
) -> DeviceInfo:
    """Return normalized identity and family info for *device_sn*.

    The bridge auto-detects the inverter family (MIN/TLX vs SPH/MIX) from the
    plant's device list and routes API calls accordingly.
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
        logger.error("device_detail(%s) failed: %s", device_sn, exc)
        raise HTTPException(status_code=502, detail=f"Growatt Cloud error: {exc}") from exc

    info = _normalize_device_info(raw, family)
    if not info.device_sn:
        info = info.model_copy(update={"device_sn": device_sn})
    if not info.plant_id:
        info = info.model_copy(update={"plant_id": resolved_plant_id})
    return info


@router.get(
    "/api/v1/devices/{device_sn}/capabilities",
    response_model=DeviceCapabilities,
    summary="Get device capabilities",
)
async def get_device_capabilities(
    device_sn: str,
    request: Request,
    plant_id: str | None = Query(
        default=None,
        description="Plant ID containing this device. Defaults to GROWATT_PLANT_ID env var.",
    ),
) -> DeviceCapabilities:
    """Describe what the bridge can read and write for *device_sn*.

    ``supported_write_operations`` lists only the operations in the current
    BRIDGE_WRITE_ALLOWLIST; it is always empty when ``readonly=true``.
    """
    client: GrowattClient = request.app.state.client
    settings: Settings = request.app.state.settings

    resolved_plant_id = await _resolve_plant_id(client, device_sn, settings, hint=plant_id)
    family = client.detect_device_family(device_sn, resolved_plant_id)

    if family is DeviceFamily.MIN:
        supported_reads = _MIN_READ_OPS
    elif family is DeviceFamily.SPH:
        supported_reads = _SPH_READ_OPS
    else:
        supported_reads = []

    if settings.bridge_readonly:
        supported_writes: list[str] = []
    else:
        try:
            allowlist = set(settings.parsed_write_allowlist())
        except ValueError:
            allowlist = set()
        supported_writes = [
            op_id
            for op_id, spec in OPERATION_REGISTRY.items()
            if op_id in allowlist and family.value in spec.supported_families
        ]

    return DeviceCapabilities(
        device_sn=device_sn,
        family=family.value,
        readonly=settings.bridge_readonly,
        supported_read_operations=supported_reads,
        supported_write_operations=supported_writes,
        has_battery=True,
        has_export_limit=True,
    )
