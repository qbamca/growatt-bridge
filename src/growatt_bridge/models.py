"""Pydantic request/response models for growatt-bridge.

All external data — Growatt Cloud API responses, HTTP request bodies, and HTTP
response bodies — passes through these models.  Field names use snake_case
throughout; the HTTP layer serialises to camelCase where needed via
``model_config``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ── TOU time-segment ──────────────────────────────────────────────────────────


class TimeSegment(BaseModel):
    """A single Time-of-Use (TOU) schedule slot on the inverter.

    MOD 12KTL3-HU supports up to 9 slots (segments 1–9).
    """

    segment: int = Field(..., ge=1, le=9, description="Slot index (1–9).")
    mode: int = Field(
        ...,
        ge=0,
        le=2,
        description="0 = load-first, 1 = battery-first, 2 = grid-first.",
    )
    start_time: str = Field(..., description="Start time in HH:MM format.")
    end_time: str = Field(..., description="End time in HH:MM format.")
    enabled: bool = Field(True, description="Whether this slot is active.")


# ── Device identity ───────────────────────────────────────────────────────────


class DeviceInfo(BaseModel):
    """Normalized device identity record returned by device list/detail endpoints."""

    device_sn: str = Field(..., description="Device serial number.")
    plant_id: str | None = Field(None, description="Parent plant ID.")
    device_type: str | None = Field(None, description="Raw device type code from Growatt.")
    family: str = Field(
        ...,
        description="Detected inverter family: MIN (MOD/TLX), SPH, or UNKNOWN.",
    )
    model: str | None = Field(None, description="Device model string, if returned by API.")
    firmware_version: str | None = Field(None, description="Firmware version string.")
    status: str | None = Field(None, description="Human-readable device status.")


# ── Device capabilities ───────────────────────────────────────────────────────


class DeviceCapabilities(BaseModel):
    """Describes what the bridge can do with a specific device.

    Returned by GET /api/v1/devices/{sn}/capabilities.
    """

    device_sn: str
    family: str
    readonly: bool = Field(
        ...,
        description="True when BRIDGE_READONLY=true; all write endpoints are disabled.",
    )
    supported_read_operations: list[str] = Field(
        default_factory=list,
        description="Read endpoint path suffixes available for this device family.",
    )
    supported_write_operations: list[str] = Field(
        default_factory=list,
        description=(
            "Write operation IDs permitted by the current allowlist. "
            "Always empty when readonly=true."
        ),
    )
    has_battery: bool = Field(True, description="Whether a battery module is detected.")
    has_export_limit: bool = Field(
        True, description="Whether export limiting is supported by device firmware."
    )


# ── Normalized telemetry ──────────────────────────────────────────────────────


class NormalizedTelemetry(BaseModel):
    """Normalized live telemetry snapshot for a MIN/TLX inverter.

    Units: power → W, energy → kWh, voltage → V, current → A,
    frequency → Hz, SOC → %, temperature → °C.

    Fields are ``None`` when absent from the API response — the Growatt API
    returns different subsets depending on firmware and device variant.
    """

    device_sn: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC time when this snapshot was taken.",
    )

    # PV input ─────────────────────────────────────────────────────────────────
    ppv: float | None = Field(None, description="Total PV input power (W).")
    vpv1: float | None = Field(None, description="PV string 1 voltage (V).")
    vpv2: float | None = Field(None, description="PV string 2 voltage (V).")
    ipv1: float | None = Field(None, description="PV string 1 current (A).")
    ipv2: float | None = Field(None, description="PV string 2 current (A).")

    # AC output ────────────────────────────────────────────────────────────────
    pac: float | None = Field(None, description="Total AC output power (W).")
    vac1: float | None = Field(None, description="AC phase 1 voltage (V).")
    vac2: float | None = Field(None, description="AC phase 2 voltage (V).")
    vac3: float | None = Field(None, description="AC phase 3 voltage (V).")
    iac1: float | None = Field(None, description="AC phase 1 current (A).")
    iac2: float | None = Field(None, description="AC phase 2 current (A).")
    iac3: float | None = Field(None, description="AC phase 3 current (A).")
    fac: float | None = Field(None, description="Grid frequency (Hz).")

    # Battery ──────────────────────────────────────────────────────────────────
    soc: float | None = Field(None, description="Battery state of charge (%).")
    p_charge: float | None = Field(None, description="Battery charge power (W).")
    p_discharge: float | None = Field(None, description="Battery discharge power (W).")
    v_bat: float | None = Field(None, description="Battery voltage (V).")
    i_bat: float | None = Field(None, description="Battery current (A).")

    # Grid import/export ───────────────────────────────────────────────────────
    p_to_grid: float | None = Field(None, description="Power exported to grid (W).")
    p_to_user: float | None = Field(None, description="Power imported from grid (W).")

    # Energy counters ──────────────────────────────────────────────────────────
    e_today: float | None = Field(None, description="PV energy generated today (kWh).")
    e_total: float | None = Field(None, description="Total PV energy generated (kWh).")
    e_charge_today: float | None = Field(None, description="Battery energy charged today (kWh).")
    e_discharge_today: float | None = Field(
        None, description="Battery energy discharged today (kWh)."
    )
    e_to_grid_today: float | None = Field(None, description="Energy exported today (kWh).")
    e_from_grid_today: float | None = Field(None, description="Energy imported today (kWh).")

    # Temperature ──────────────────────────────────────────────────────────────
    temp1: float | None = Field(None, description="Inverter temperature sensor 1 (°C).")
    temp2: float | None = Field(None, description="Inverter temperature sensor 2 (°C).")

    # Status ───────────────────────────────────────────────────────────────────
    status_code: int | None = Field(None, description="Raw inverter status integer.")
    status_text: str | None = Field(None, description="Human-readable inverter status.")
    lost: bool = Field(False, description="True when the device is offline/unreachable.")

    # Raw source data (excluded from serialization; available for debugging)
    raw: dict[str, Any] | None = Field(None, exclude=True)


# ── Normalized configuration ──────────────────────────────────────────────────


class NormalizedConfig(BaseModel):
    """Normalized current configuration snapshot for a MIN/TLX inverter.

    Returned by GET /api/v1/devices/{sn}/config and included in write
    readbacks.  Fields are ``None`` when the API does not expose them for
    the connected device variant.
    """

    device_sn: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC time when this snapshot was taken.",
    )

    # Battery charge/discharge limits ──────────────────────────────────────────
    charge_power_rate: int | None = Field(
        None, description="Max charge power as % of rated capacity (0–100)."
    )
    discharge_power_rate: int | None = Field(
        None, description="Max discharge power as % of rated capacity (0–100)."
    )
    discharge_stop_soc: int | None = Field(
        None, description="Minimum SOC below which discharge is stopped (10–100)."
    )

    # AC charge (grid → battery) ───────────────────────────────────────────────
    ac_charge_enabled: bool | None = Field(
        None, description="Whether the inverter will charge the battery from the grid."
    )
    ac_charge_stop_soc: int | None = Field(
        None, description="SOC at which AC charging automatically stops (10–100)."
    )

    # Export limit ─────────────────────────────────────────────────────────────
    export_limit_enabled: bool | None = Field(
        None, description="Whether export power limiting is active."
    )
    export_limit_power_rate: int | None = Field(
        None, description="Export power cap as % of rated capacity (0–100)."
    )

    # TOU schedule ─────────────────────────────────────────────────────────────
    time_segments: list[TimeSegment] = Field(
        default_factory=list,
        description="TOU schedule slots 1–9; empty when API does not return them.",
    )

    # Raw source data
    raw: dict[str, Any] | None = Field(None, exclude=True)


# ── Write command request / response ──────────────────────────────────────────


class CommandRequest(BaseModel):
    """Request body for POST /api/v1/devices/{sn}/commands/{operation_id}.

    The ``params`` dict contents depend on the operation.  Refer to the
    ``OPERATION_REGISTRY`` in ``safety.py`` for each operation's expected keys.
    """

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Operation-specific parameters. See docs/parameters/ for valid keys.",
    )


class ReadbackDiff(BaseModel):
    """Comparison between pre-write and post-write configuration.

    Attached to every ``CommandResponse`` when ``BRIDGE_REQUIRE_READBACK=true``.
    """

    changed: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Fields whose value changed after the write: "
            "{field_name: {before: old_value, after: new_value}}."
        ),
    )
    unchanged: list[str] = Field(
        default_factory=list,
        description="Config fields that were read back but whose value did not change.",
    )
    readback_failed: bool = Field(
        False,
        description=(
            "True when the post-write re-read failed or the parameter is not "
            "directly readable via the current API.  The write may still have succeeded."
        ),
    )
    readback_error: str | None = Field(
        None,
        description="Error message from the failed readback attempt, if any.",
    )


class CommandResponse(BaseModel):
    """Response for POST /api/v1/devices/{sn}/commands/{operation_id}.

    Also returned by the /validate dry-run endpoint (with ``success`` reflecting
    validation outcome, not actual hardware change).
    """

    success: bool = Field(..., description="True when the write was accepted by Growatt Cloud.")
    operation: str = Field(..., description="Operation ID that was executed.")
    device_sn: str
    params_sent: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters as forwarded to the Growatt API (after validation/normalisation).",
    )
    raw_response: dict[str, Any] | None = Field(
        None,
        description="Raw JSON response from growattServer (may be None on timeout/error).",
    )
    readback: ReadbackDiff | None = Field(
        None,
        description=(
            "Config diff captured after the write. "
            "None when BRIDGE_REQUIRE_READBACK=false."
        ),
    )
    audit_id: str = Field(
        ...,
        description="UUID identifying the audit log entry for this operation.",
    )
    error: str | None = Field(
        None,
        description="Human-readable error message when success=false.",
    )


class ValidateResponse(BaseModel):
    """Response for POST /api/v1/devices/{sn}/commands/{operation_id}/validate.

    Performs all safety and parameter validation without sending anything to
    the Growatt Cloud API.
    """

    valid: bool
    operation: str
    device_sn: str
    params: dict[str, Any]
    errors: list[str] = Field(
        default_factory=list,
        description="Validation error messages; empty when valid=true.",
    )


# ── Plant models ──────────────────────────────────────────────────────────────


class PlantSummary(BaseModel):
    """Minimal plant record returned in list responses."""

    plant_id: str
    plant_name: str | None = None
    total_power: float | None = Field(
        None, description="Current total generation power for the plant (W)."
    )
    status: str | None = None


class PlantDetail(PlantSummary):
    """Full plant record returned by GET /api/v1/plants/{plant_id}."""

    devices: list[DeviceInfo] = Field(default_factory=list)
    raw: dict[str, Any] | None = Field(None, exclude=True)


# ── Write operations catalog (GET /api/v1/write-operations) ─────────────────


class WriteOperationCatalogItem(BaseModel):
    """One named write operation derived from the safety-layer registry."""

    operation_id: str
    description: str
    supported_families: list[str]
    params_schema: dict[str, Any] = Field(
        ...,
        description="Structured parameter shape (scalar or time_segment).",
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Reserved for operations that need extra caller acknowledgments.",
    )
    currently_permitted: bool | None = Field(
        None,
        description="Present when include_policy=true: allowed by readonly + allowlist.",
    )


class WriteOperationsCatalogResponse(BaseModel):
    """Full catalog of write operations for agent discovery."""

    operations: list[WriteOperationCatalogItem]
    readonly: bool | None = Field(
        None,
        description="Mirrors BRIDGE_READONLY when include_policy=true.",
    )
    allowlist_parse_error: str | None = Field(
        None,
        description="Set when BRIDGE_WRITE_ALLOWLIST is invalid (include_policy=true).",
    )


# ── Standard error response ───────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard JSON error envelope for all 4xx/5xx responses."""

    error: str = Field(..., description="Short machine-readable error type.")
    detail: str | None = Field(None, description="Human-readable explanation.")
    operation: str | None = Field(
        None, description="Operation ID involved, if applicable."
    )
