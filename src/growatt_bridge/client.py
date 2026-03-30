"""Thin wrapper around growattServer.OpenApiV1.

Responsibilities:
- Construct the client from Settings (token + regional URL).
- Provide a typed DeviceFamily enum so the rest of the bridge doesn't
  hardcode string device-type literals.
- Auto-detect device family (MIN/TLX = type 7, SPH/MIX = type 5) from the
  plant's device list and expose per-family read/write dispatch helpers.
- Redact the API token in all log/repr output.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ── Device family ──────────────────────────────────────────────────────────────

# Growatt Cloud device-type integers from the device_list API response.
_MIN_DEVICE_TYPE = 7   # MIN / TLX family (MOD 12KTL3-HU, etc.)
_SPH_DEVICE_TYPE = 5   # SPH / MIX hybrid family


class DeviceFamily(str, Enum):
    """Detected inverter family, used to route API calls."""

    MIN = "MIN"   # min_* methods, v1/tlxSet writes
    SPH = "SPH"   # sph_* methods
    UNKNOWN = "UNKNOWN"


def _device_family_from_type(device_type: int | str | None) -> DeviceFamily:
    """Map a raw device-type integer to a DeviceFamily."""
    try:
        t = int(device_type)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DeviceFamily.UNKNOWN
    if t == _MIN_DEVICE_TYPE:
        return DeviceFamily.MIN
    if t == _SPH_DEVICE_TYPE:
        return DeviceFamily.SPH
    return DeviceFamily.UNKNOWN


# ── growattServer import guard ─────────────────────────────────────────────────

try:
    import growattServer  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "growattServer is not installed. Run: pip install growattServer>=1.9.0"
    ) from exc


def format_growatt_cloud_error(exc: BaseException) -> str:
    """Format a Growatt SDK error for logs and HTTP responses (no secrets).

    ``growattServer.GrowattV1ApiError`` carries ``error_code`` and ``error_msg``
    from the OpenAPI JSON body; the exception's ``str()`` alone is often generic
    (e.g. \"Error during getting plant list\").
    """

    v1_cls = getattr(growattServer, "GrowattV1ApiError", None)
    if isinstance(v1_cls, type) and isinstance(exc, v1_cls):
        base = str(exc).strip()
        parts: list[str] = []
        if exc.error_code is not None:
            parts.append(f"error_code={exc.error_code}")
        if exc.error_msg:
            parts.append(f"error_msg={exc.error_msg!r}")
        if parts:
            return f"{base} ({', '.join(parts)})"
        return base
    return str(exc)


# ── Client wrapper ─────────────────────────────────────────────────────────────

class GrowattClient:
    """Stateless wrapper around growattServer.OpenApiV1.

    All calls to Growatt Cloud go through this object.  The wrapper:
    - Never logs or exposes the raw API token.
    - Normalises plant/device-list responses to consistent dicts.
    - Detects and caches device family per serial number.
    """

    def __init__(self, token: str, server_url: str) -> None:
        self._token = token
        self._server_url = server_url.rstrip("/") + "/"
        self._api = self._build_api()
        # Cache: sn → DeviceFamily (populated by detect_device_family)
        self._family_cache: dict[str, DeviceFamily] = {}

    # -- Construction ----------------------------------------------------------

    def _build_api(self) -> Any:
        api = growattServer.OpenApiV1(token=self._token)
        api.server_url = self._server_url
        # OpenApiV1 computes api_url at __init__ time before server_url is overridden.
        # Re-set it so V1 get_url() calls hit the correct host.
        api.api_url = self._server_url + "v1/"
        return api

    # -- Repr / logging --------------------------------------------------------

    def __repr__(self) -> str:
        token_hint = (
            self._token[:4] + "***" if len(self._token) > 4 else "***"
        )
        return f"GrowattClient(server_url={self._server_url!r}, token={token_hint!r})"

    # -- Plant helpers ---------------------------------------------------------

    def plant_list(self) -> list[dict[str, Any]]:
        """Return the list of plants accessible by the token."""
        raw = self._api.plant_list()
        return _extract_list(raw, "plants")

    def plant_details(self, plant_id: str) -> dict[str, Any]:
        """Return details for a single plant."""
        return self._api.plant_details(plant_id) or {}

    # -- Device helpers --------------------------------------------------------

    def device_list(self, plant_id: str) -> list[dict[str, Any]]:
        """Return the list of devices in a plant."""
        raw = self._api.device_list(plant_id)
        return _extract_list(raw, "devices")

    def detect_device_family(self, device_sn: str, plant_id: str) -> DeviceFamily:
        """Detect and cache the DeviceFamily for *device_sn*.

        Queries device_list for the plant and inspects the deviceType field.
        Returns DeviceFamily.UNKNOWN if the serial is not found.
        """
        if device_sn in self._family_cache:
            return self._family_cache[device_sn]

        devices = self.device_list(plant_id)
        for dev in devices:
            sn = _sn(dev)
            raw_type = dev.get("deviceType") or dev.get("type") or dev.get("device_type")
            family = _device_family_from_type(raw_type)
            if sn:
                self._family_cache[sn] = family

        result = self._family_cache.get(device_sn, DeviceFamily.UNKNOWN)
        if result is DeviceFamily.UNKNOWN:
            logger.warning(
                "Device %s not found in plant %s device list; defaulting to UNKNOWN family.",
                device_sn,
                plant_id,
            )
        return result

    # -- Telemetry reads -------------------------------------------------------

    def device_detail(self, device_sn: str, family: DeviceFamily) -> dict[str, Any]:
        """Fetch live detail for an inverter, routed by family."""
        if family is DeviceFamily.MIN:
            return self._api.min_detail(device_sn) or {}
        if family is DeviceFamily.SPH:
            return self._api.sph_detail(device_sn) or {}
        raise UnsupportedDeviceFamilyError(device_sn, family)

    def device_energy(self, device_sn: str, family: DeviceFamily) -> dict[str, Any]:
        """Fetch energy summary for an inverter, routed by family."""
        if family is DeviceFamily.MIN:
            return self._api.min_energy(device_sn) or {}
        if family is DeviceFamily.SPH:
            return self._api.sph_energy(device_sn) or {}
        raise UnsupportedDeviceFamilyError(device_sn, family)

    # -- Config reads ----------------------------------------------------------

    def read_time_segments(self, device_sn: str, family: DeviceFamily) -> list[dict[str, Any]]:
        """Read all TOU time-segment slots from the inverter.

        Returns a list of up to 9 segment dicts.  Only MIN family is
        first-class; SPH is not yet mapped.
        """
        if family is DeviceFamily.MIN:
            raw = self._api.min_read_time_segment(device_sn)
            return _extract_list(raw, "timeSegments") or ([raw] if raw else [])
        raise UnsupportedDeviceFamilyError(device_sn, family)

    # -- Write dispatch (called by safety layer, never directly) ---------------

    def min_write_time_segment(
        self,
        device_sn: str,
        segment: int,
        mode: int,
        start_time: str,
        end_time: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Write a single TOU segment on a MIN/TLX device."""
        st = (
            start_time
            if hasattr(start_time, "hour")
            else datetime.strptime(str(start_time).strip(), "%H:%M").time()
        )
        et = (
            end_time
            if hasattr(end_time, "hour")
            else datetime.strptime(str(end_time).strip(), "%H:%M").time()
        )
        return (
            self._api.min_write_time_segment(
                device_sn,
                segment,
                mode,
                st,
                et,
                enabled,
            )
            or {}
        )

    def min_write_parameter(
        self, device_sn: str, parameter_id: str, value: str
    ) -> dict[str, Any]:
        """Write a named parameter on a MIN/TLX device.

        NOTE: This method is intentionally NOT exposed through any HTTP route.
        The safety layer calls it only via named write operations with
        hardcoded parameter IDs; arbitrary parameter_id passthrough is
        never permitted at the HTTP layer.
        """
        return self._api.min_write_parameter(device_sn, parameter_id, value) or {}

    # -- Raw API access (for scripts / testing only) ---------------------------

    @property
    def raw_api(self) -> Any:
        """Direct access to the underlying growattServer.OpenApiV1 instance.

        Use only in scripts and tests.  Production routes must go through the
        typed helpers above so that token redaction and logging are consistent.
        """
        return self._api


# ── Errors ────────────────────────────────────────────────────────────────────

class UnsupportedDeviceFamilyError(Exception):
    """Raised when a requested operation is not supported for a device family."""

    def __init__(self, device_sn: str, family: DeviceFamily) -> None:
        super().__init__(
            f"Operation not supported for device {device_sn!r} (family={family.value})."
        )
        self.device_sn = device_sn
        self.family = family


# ── Factory ───────────────────────────────────────────────────────────────────

def build_client_from_settings(settings: Any) -> GrowattClient:
    """Construct a GrowattClient from a Settings instance.

    Accepts the Settings object (defined in config.py) to avoid a circular
    import while keeping the factory co-located with the client.
    """
    return GrowattClient(
        token=settings.growatt_api_token,
        server_url=settings.growatt_server_url,
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _extract_list(raw: Any, key: str) -> list[dict[str, Any]]:
    """Pull a list from a dict response, or return the value itself if already a list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        value = raw.get(key)
        if isinstance(value, list):
            return value
        # Some endpoints nest under a second 'data' key
        data = raw.get("data")
        if isinstance(data, dict):
            nested = data.get(key)
            if isinstance(nested, list):
                return nested
        if isinstance(data, list):
            return data
    return []


def _sn(device: dict[str, Any]) -> str | None:
    """Extract the serial number from a device dict, trying multiple key names."""
    return (
        device.get("device_sn")
        or device.get("deviceSn")
        or device.get("serialNum")
        or device.get("sn")
    )
