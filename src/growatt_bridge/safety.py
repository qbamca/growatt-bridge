"""Write allowlist enforcement, parameter validation, rate limiting, and audit logging.

Architecture:
    HTTP Route → SafetyLayer → GrowattClient → Growatt Cloud

The ``SafetyLayer`` is the only path through which write operations reach the
client.  Routes MUST NOT call client write methods directly.

Design principles:
- Default readonly.  Writes require ``BRIDGE_READONLY=false`` AND an explicit
  allowlist entry.
- Named operations only.  There is no passthrough for raw ``parameter_id``
  values — every write maps to a hardcoded spec with bounded parameters.
- Per-operation range validation.  Values are checked before the API call.
- Sliding-window rate limiting.  In-memory, resets on restart.
- Append-only audit log.  Every write attempt (success or failure) is
  recorded as a JSONL entry with timestamp, operation, params, and result.
  The API token is NEVER written to the audit log or any exception message.
- Post-write readback.  After a write, the relevant config is re-read and a
  diff is attached to the response.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .client import DeviceFamily, GrowattClient, UnsupportedDeviceFamilyError
from .config import Settings
from .legacy_shine_web import LegacyShineWebClient
from .models import CommandResponse, ReadbackDiff

logger = logging.getLogger(__name__)


# ── Errors ────────────────────────────────────────────────────────────────────


class WriteNotPermittedError(Exception):
    """Raised when a write is blocked by safety policy (readonly or not allowlisted)."""


class OperationValidationError(Exception):
    """Raised when operation parameters fail pre-flight validation."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class RateLimitError(Exception):
    """Raised when the configured write rate limit would be exceeded."""


class UnknownOperationError(Exception):
    """Raised when an operation ID is not in the registry."""


# ── Operation specifications ──────────────────────────────────────────────────


@dataclass
class _ParamSpec:
    """Specification for a single min_write_parameter-style operation.

    ``parameter_id`` is the exact string passed to ``min_write_parameter``.
    It is hardcoded here and never exposed to callers.

    ``legacy_web_type`` is the Shine web ``tcpSet.do`` form field ``type`` when
    ``bridge_legacy_web_min_writes`` is enabled (see docs/growatt-cloud-api.md).
    """

    parameter_id: str
    legacy_web_type: str
    value_key: str = "value"
    min_val: int | float | None = None
    max_val: int | float | None = None
    # When True, the value_key must be a bool; API receives "1" or "0".
    is_bool: bool = False


@dataclass
class _OperationSpec:
    """Full specification for a named write operation."""

    operation_id: str
    description: str
    supported_families: tuple[str, ...] = ("MIN",)
    # For min_write_parameter-style writes:
    param_spec: _ParamSpec | None = None
    # For time-segment writes (custom dispatch path):
    is_time_segment: bool = False
    # Optional extra guard callables: (params) → error_str | None
    extra_guards: list[Callable[[dict[str, Any]], str | None]] = field(
        default_factory=list
    )


# ── Extra guards ──────────────────────────────────────────────────────────────


def _legacy_min_write_prerequisite_errors(
    settings: Settings,
    plant_id: str | None,
    family: DeviceFamily,
) -> list[str]:
    """Return validation errors when legacy web MIN writes are enabled but prerequisites are missing."""
    if not settings.bridge_legacy_web_min_writes:
        return []
    if family is not DeviceFamily.MIN:
        return []
    errors: list[str] = []
    if not plant_id or not str(plant_id).strip():
        errors.append(
            "Legacy web writes require a resolved plant ID "
            "(pass the plant_id query parameter on the command URL or set GROWATT_PLANT_ID)."
        )
    if not settings.growatt_web_username or not settings.growatt_web_password:
        errors.append(
            "Legacy web writes require GROWATT_WEB_USERNAME and GROWATT_WEB_PASSWORD."
        )
    return errors


# ── Operation registry ────────────────────────────────────────────────────────
#
# This is the ONLY place where parameter_id strings and value constraints live.
# Routes must reference operations by their operation_id key only.
#
# Parameter IDs are from the Growatt OpenAPI V1 / growattServer library.
# Legacy web ``type`` strings differ from OpenAPI parameter_id; mapping table:
# docs/growatt-cloud-api.md § Legacy tcpSet.do type mapping.

# Only operations that have been exercised end-to-end against real hardware belong
# here. Add more entries only after integration testing.
OPERATION_REGISTRY: dict[str, _OperationSpec] = {
    "set_ac_charge_stop_soc": _OperationSpec(
        operation_id="set_ac_charge_stop_soc",
        description="Set SOC target at which AC (grid) charging automatically stops (10–100).",
        param_spec=_ParamSpec(
            parameter_id="ac_charge_soc_limit",
            legacy_web_type="ub_ac_charging_stop_soc",
            min_val=10,
            max_val=100,
        ),
    ),
}


# ── Write operations catalog (LLM / agent discovery) ──────────────────────────


def _params_schema_for_spec(spec: _OperationSpec) -> dict[str, Any]:
    """Build a JSON-serializable params schema for *spec*."""
    if spec.is_time_segment:
        return {
            "kind": "time_segment",
            "fields": [
                {
                    "name": "segment",
                    "type": "integer",
                    "required": True,
                    "min": 1,
                    "max": 9,
                },
                {
                    "name": "mode",
                    "type": "integer",
                    "required": True,
                    "min": 0,
                    "max": 2,
                    "enum_meaning": {
                        "0": "load_first",
                        "1": "battery_first",
                        "2": "grid_first",
                    },
                },
                {
                    "name": "start_time",
                    "type": "string",
                    "required": True,
                    "format": "HH:MM",
                    "description": "Start boundary (00:00–23:59).",
                },
                {
                    "name": "end_time",
                    "type": "string",
                    "required": True,
                    "format": "HH:MM",
                    "description": "End boundary (00:00–23:59).",
                },
                {
                    "name": "enabled",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
            ],
        }

    assert spec.param_spec is not None  # noqa: S101
    ps = spec.param_spec
    if ps.is_bool:
        field_type = "boolean"
    else:
        field_type = "number"
    field: dict[str, Any] = {
        "name": ps.value_key,
        "type": field_type,
        "required": True,
    }
    if ps.min_val is not None:
        field["min"] = ps.min_val
    if ps.max_val is not None:
        field["max"] = ps.max_val
    return {"kind": "scalar", "fields": [field]}


def _constraints_for_spec(_spec: _OperationSpec) -> dict[str, Any]:
    return {"requires_meter_acknowledgment": False}


def _currently_permitted(
    operation_id: str,
    *,
    readonly: bool,
    allowed: set[str] | None,
) -> bool:
    if readonly or allowed is None:
        return False
    return operation_id in allowed


def build_write_operations_catalog(
    *,
    include_policy: bool,
    settings: Settings | None,
) -> dict[str, Any]:
    """Return a JSON-serializable catalog of all registered write operations.

    When *include_policy* is True and *settings* is provided, each operation
    includes ``currently_permitted`` (readonly + allowlist).  Invalid
    ``BRIDGE_WRITE_ALLOWLIST`` env values yield ``allowlist_parse_error`` and
    no permitted operations.
    """
    readonly: bool | None = None
    allowed: set[str] | None = None
    allowlist_parse_error: str | None = None

    if include_policy and settings is not None:
        readonly = settings.bridge_readonly
        if readonly:
            allowed = set()
        else:
            try:
                allowed = set(settings.parsed_write_allowlist())
            except ValueError as exc:
                allowlist_parse_error = str(exc)
                allowed = set()

    operations: list[dict[str, Any]] = []
    for op_id in sorted(OPERATION_REGISTRY.keys()):
        spec = OPERATION_REGISTRY[op_id]
        entry: dict[str, Any] = {
            "operation_id": spec.operation_id,
            "description": spec.description,
            "supported_families": list(spec.supported_families),
            "params_schema": _params_schema_for_spec(spec),
            "constraints": _constraints_for_spec(spec),
        }
        if include_policy and settings is not None:
            entry["currently_permitted"] = _currently_permitted(
                op_id,
                readonly=bool(readonly),
                allowed=allowed,
            )
        operations.append(entry)

    result: dict[str, Any] = {"operations": operations}
    if include_policy and settings is not None:
        result["readonly"] = readonly
        result["allowlist_parse_error"] = allowlist_parse_error
    return result


# ── Rate limiter ──────────────────────────────────────────────────────────────


class _SlidingWindowRateLimiter:
    """Thread-safe sliding-window write rate limiter.

    Tracks the timestamps of recent write attempts and refuses new ones once
    ``max_calls`` have occurred within the rolling ``window_seconds`` window.
    State is in-memory and resets on service restart.
    """

    def __init__(self, max_calls: int, window_seconds: int = 60) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._timestamps: deque[datetime] = deque()
        self._lock = threading.Lock()

    def check_and_record(self) -> bool:
        """Check whether a write is allowed under the current rate limit.

        If allowed, records the current timestamp and returns True.
        Returns False if the limit would be exceeded.
        """
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - self._window_seconds

        with self._lock:
            # Purge timestamps outside the current window
            while self._timestamps and self._timestamps[0].timestamp() < cutoff:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max_calls:
                return False

            self._timestamps.append(now)
            return True

    @property
    def current_count(self) -> int:
        """Number of writes recorded in the current window (thread-safe snapshot)."""
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - self._window_seconds
        with self._lock:
            return sum(1 for ts in self._timestamps if ts.timestamp() >= cutoff)


# ── Audit logger ──────────────────────────────────────────────────────────────


class _AuditLogger:
    """Append-only JSONL audit logger.

    Every write attempt (successful or not) is recorded as a single-line JSON
    object.  The log file is created (including parent directories) on first
    write.  Write failures are logged as warnings but never raise — we do not
    want audit log I/O to crash the bridge.

    The API token is NEVER written to the log.
    """

    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._lock = threading.Lock()
        self._initialised = False

    def _ensure_path(self) -> bool:
        """Create the log directory and file if they don't exist.

        Returns False if setup fails (non-fatal).
        """
        if self._initialised:
            return True
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch(exist_ok=True)
            self._initialised = True
            return True
        except OSError as exc:
            logger.warning(
                "Audit log setup failed for %s: %s. Audit entries will not be persisted.",
                self._path,
                exc,
            )
            return False

    def record(self, entry: dict[str, Any]) -> str:
        """Append *entry* to the audit log and return the audit_id.

        Assigns a UUID ``audit_id`` if not already present in *entry*.
        """
        audit_id = entry.setdefault("audit_id", str(uuid.uuid4()))
        entry.setdefault("logged_at", datetime.now(timezone.utc).isoformat())

        # Defensive: ensure token is never written
        entry.pop("token", None)
        entry.pop("api_token", None)
        entry.pop("growatt_api_token", None)

        with self._lock:
            if not self._ensure_path():
                return audit_id
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, default=str) + "\n")
            except OSError as exc:
                logger.warning("Failed to write audit log entry %s: %s", audit_id, exc)

        return audit_id


# ── Safety layer ──────────────────────────────────────────────────────────────


class SafetyLayer:
    """Central write-control layer for the growatt-bridge.

    All write operations MUST flow through ``execute_write``.  This class
    enforces readonly mode, the write allowlist, parameter validation, rate
    limiting, audit logging, and post-write readback.
    """

    def __init__(self, settings: Settings, client: GrowattClient) -> None:
        self._settings = settings
        self._client = client
        self._rate_limiter = _SlidingWindowRateLimiter(
            max_calls=settings.bridge_rate_limit_writes,
            window_seconds=60,
        )
        self._audit = _AuditLogger(settings.bridge_audit_log)
        self._legacy_lock = threading.Lock()
        self._legacy_client: LegacyShineWebClient | None = None

    def _get_legacy_client(self) -> LegacyShineWebClient | None:
        """Lazily construct the legacy web client when the feature flag and credentials are set."""
        if not self._settings.bridge_legacy_web_min_writes:
            return None
        u, p = self._settings.growatt_web_username, self._settings.growatt_web_password
        if not u or not p:
            return None
        with self._legacy_lock:
            if self._legacy_client is None:
                self._legacy_client = LegacyShineWebClient(
                    self._settings.growatt_web_base_url,
                    u,
                    p,
                )
            return self._legacy_client

    # ── Public interface ───────────────────────────────────────────────────────

    def check_write_permitted(self, operation_id: str) -> None:
        """Raise ``WriteNotPermittedError`` if the operation is blocked.

        Checks (in order):
        1. Bridge is not in readonly mode.
        2. operation_id is a known operation.
        3. operation_id is in the configured allowlist.
        """
        if self._settings.bridge_readonly:
            raise WriteNotPermittedError(
                "Bridge is in readonly mode (BRIDGE_READONLY=true). "
                "Set BRIDGE_READONLY=false and configure BRIDGE_WRITE_ALLOWLIST to enable writes."
            )

        if operation_id not in OPERATION_REGISTRY:
            raise UnknownOperationError(
                f"Unknown operation {operation_id!r}. "
                f"Valid IDs: {sorted(OPERATION_REGISTRY)}"
            )

        if not self._settings.is_operation_allowed(operation_id):
            raise WriteNotPermittedError(
                f"Operation {operation_id!r} is not in BRIDGE_WRITE_ALLOWLIST. "
                f"Add it to the allowlist to permit this write."
            )

    def validate_params(
        self,
        operation_id: str,
        params: dict[str, Any],
        *,
        plant_id: str | None = None,
        family: DeviceFamily | None = None,
    ) -> list[str]:
        """Return a list of validation error strings for *params* against *operation_id*.

        An empty list means all checks passed.  Raises ``UnknownOperationError``
        if operation_id is not registered.
        """
        if operation_id not in OPERATION_REGISTRY:
            raise UnknownOperationError(
                f"Unknown operation {operation_id!r}. "
                f"Valid IDs: {sorted(OPERATION_REGISTRY)}"
            )

        spec = OPERATION_REGISTRY[operation_id]
        errors: list[str] = []

        if spec.is_time_segment:
            errors.extend(_validate_time_segment_params(params))
        elif spec.param_spec is not None:
            errors.extend(_validate_parameter_params(spec.param_spec, params))

        for guard in spec.extra_guards:
            msg = guard(params)
            if msg:
                errors.append(msg)

        if family is not None:
            errors.extend(
                _legacy_min_write_prerequisite_errors(self._settings, plant_id, family)
            )

        return errors

    def execute_write(
        self,
        operation_id: str,
        device_sn: str,
        family: DeviceFamily,
        params: dict[str, Any],
        *,
        plant_id: str | None = None,
    ) -> CommandResponse:
        """Execute a write operation through the full safety pipeline.

        Flow:
        1. Permission check (readonly + allowlist)
        2. Family compatibility check
        3. Parameter validation
        4. Rate limit check
        5. Execute via GrowattClient
        6. Audit log
        7. Optional readback
        8. Return CommandResponse

        Never raises for API-level failures — these are captured in
        ``CommandResponse.success=False`` and logged to audit.

        Raises:
            WriteNotPermittedError: readonly mode or not allowlisted.
            UnknownOperationError: operation_id not in registry.
            OperationValidationError: params failed validation.
            RateLimitError: write rate limit exceeded.
            UnsupportedDeviceFamilyError: operation not supported for family.
        """
        # 1. Permission check
        self.check_write_permitted(operation_id)

        spec = OPERATION_REGISTRY[operation_id]

        # 2. Family compatibility
        if family.value not in spec.supported_families:
            raise UnsupportedDeviceFamilyError(device_sn, family)

        # 3. Validate params
        errors = self.validate_params(
            operation_id, params, plant_id=plant_id, family=family
        )
        if errors:
            raise OperationValidationError(errors)

        # 4. Rate limit
        if not self._rate_limiter.check_and_record():
            raise RateLimitError(
                f"Write rate limit exceeded "
                f"({self._settings.bridge_rate_limit_writes} writes/min). "
                "Wait before retrying."
            )

        # 5. Execute
        audit_id = str(uuid.uuid4())
        raw_response: dict[str, Any] | None = None
        success = False
        error_msg: str | None = None
        params_sent: dict[str, Any] = {}

        try:
            raw_response, params_sent = self._dispatch_write(
                spec, device_sn, family, params, plant_id=plant_id
            )
            success = _is_api_success(raw_response)
            if not success:
                error_msg = _extract_api_error(raw_response)
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Growatt API call failed: {type(exc).__name__}: {exc}"
            logger.error(
                "Write operation %r on %s failed: %s",
                operation_id,
                device_sn,
                error_msg,
            )

        # 6. Audit
        self._audit.record(
            {
                "audit_id": audit_id,
                "operation": operation_id,
                "device_sn": device_sn,
                "family": family.value,
                "params_sent": params_sent,
                "success": success,
                "raw_response": raw_response,
                "error": error_msg,
            }
        )

        # 7. Readback
        readback: ReadbackDiff | None = None
        if self._settings.bridge_require_readback and success:
            readback = self._attempt_readback(spec, device_sn, family, params_sent)

        return CommandResponse(
            success=success,
            operation=operation_id,
            device_sn=device_sn,
            params_sent=params_sent,
            raw_response=raw_response,
            readback=readback,
            audit_id=audit_id,
            error=error_msg,
        )

    def dry_run_validate(
        self,
        operation_id: str,
        device_sn: str,
        family: DeviceFamily,
        params: dict[str, Any],
        *,
        plant_id: str | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate an operation without executing it.

        Returns (valid, errors).  Checks permission, family, and param
        validation.  Does NOT check the rate limit (dry runs are free).
        """
        try:
            self.check_write_permitted(operation_id)
        except (WriteNotPermittedError, UnknownOperationError) as exc:
            return False, [str(exc)]

        spec = OPERATION_REGISTRY[operation_id]
        if family.value not in spec.supported_families:
            return False, [
                f"Operation {operation_id!r} is not supported for device family {family.value}."
            ]

        errors = self.validate_params(
            operation_id, params, plant_id=plant_id, family=family
        )
        return (len(errors) == 0), errors

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _dispatch_write(
        self,
        spec: _OperationSpec,
        device_sn: str,
        family: DeviceFamily,
        params: dict[str, Any],
        *,
        plant_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Call the appropriate GrowattClient method; return (raw_response, params_sent)."""
        if spec.is_time_segment:
            return self._write_time_segment(device_sn, params, plant_id=plant_id)

        assert spec.param_spec is not None  # noqa: S101 – guaranteed by registry
        return self._write_parameter(
            spec.param_spec, device_sn, params, plant_id=plant_id
        )

    def _write_time_segment(
        self,
        device_sn: str,
        params: dict[str, Any],
        *,
        plant_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        segment = int(params["segment"])
        mode = int(params["mode"])
        start_time = params["start_time"]
        end_time = params["end_time"]
        enabled = bool(params.get("enabled", True))

        params_sent = {
            "segment": segment,
            "mode": mode,
            "start_time": start_time,
            "end_time": end_time,
            "enabled": enabled,
        }

        if self._settings.bridge_legacy_web_min_writes:
            legacy = self._get_legacy_client()
            if legacy is None:
                raise RuntimeError(
                    "Legacy web MIN writes are enabled but Shine web credentials are missing."
                )
            if not plant_id or not str(plant_id).strip():
                raise RuntimeError(
                    "Legacy web MIN writes require a resolved plant_id (query param or GROWATT_PLANT_ID)."
                )
            sh, sm = _hhmm_to_hour_minute(str(start_time))
            eh, em = _hhmm_to_hour_minute(str(end_time))
            raw = legacy.tcp_set_time_segment(
                str(plant_id).strip(),
                device_sn,
                segment,
                mode,
                sh,
                sm,
                eh,
                em,
                enabled,
            )
        else:
            raw = self._client.min_write_time_segment(
                device_sn,
                segment=segment,
                mode=mode,
                start_time=start_time,
                end_time=end_time,
                enabled=enabled,
            )
        return raw, params_sent

    def _write_parameter(
        self,
        param_spec: _ParamSpec,
        device_sn: str,
        params: dict[str, Any],
        *,
        plant_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        raw_value = params[param_spec.value_key]

        if param_spec.is_bool:
            api_value = "1" if raw_value else "0"
        else:
            api_value = str(int(raw_value))

        params_sent = {
            param_spec.value_key: raw_value,
            "_parameter_id": param_spec.parameter_id,
            "_api_value": api_value,
            "_legacy_web_type": param_spec.legacy_web_type,
        }

        if self._settings.bridge_legacy_web_min_writes:
            legacy = self._get_legacy_client()
            if legacy is None:
                raise RuntimeError(
                    "Legacy web MIN writes are enabled but Shine web credentials are missing."
                )
            if not plant_id or not str(plant_id).strip():
                raise RuntimeError(
                    "Legacy web MIN writes require a resolved plant_id (query param or GROWATT_PLANT_ID)."
                )
            raw = legacy.tcp_set_scalar(
                str(plant_id).strip(),
                device_sn,
                param_spec.legacy_web_type,
                api_value,
            )
        else:
            raw = self._client.min_write_parameter(
                device_sn, param_spec.parameter_id, api_value
            )
        return raw, params_sent

    def _attempt_readback(
        self,
        spec: _OperationSpec,
        device_sn: str,
        family: DeviceFamily,
        params_sent: dict[str, Any],
    ) -> ReadbackDiff:
        """Attempt to re-read relevant config and produce a diff.

        For time-segment writes: re-reads all segments and checks the target slot.
        For parameter writes: calls device_detail for a best-effort check.
        Returns a ReadbackDiff with readback_failed=True on I/O error.
        """
        try:
            if spec.is_time_segment:
                return self._readback_time_segment(device_sn, family, params_sent)
            return self._readback_parameter(spec, device_sn, family, params_sent)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Post-write readback failed for %s on %s: %s",
                spec.operation_id,
                device_sn,
                exc,
            )
            return ReadbackDiff(
                readback_failed=True,
                readback_error=f"{type(exc).__name__}: {exc}",
            )

    def _readback_time_segment(
        self,
        device_sn: str,
        family: DeviceFamily,
        params_sent: dict[str, Any],
    ) -> ReadbackDiff:
        segments = self._client.read_time_segments(device_sn, family)
        target_idx = int(params_sent["segment"])

        # Find the segment with the matching index
        matched: dict[str, Any] | None = None
        for seg in segments:
            seg_num = seg.get("segment") or seg.get("segmentNum") or seg.get("num")
            try:
                if int(seg_num) == target_idx:  # type: ignore[arg-type]
                    matched = seg
                    break
            except (TypeError, ValueError):
                continue

        if matched is None:
            return ReadbackDiff(
                readback_failed=True,
                readback_error=f"Segment {target_idx} not found in readback response.",
            )

        # Build diff between what we sent and what we read back
        changed: dict[str, Any] = {}
        unchanged: list[str] = []

        field_map = {
            "mode": ("mode",),
            "start_time": ("start_time", "startTime"),
            "end_time": ("end_time", "endTime"),
            "enabled": ("enabled",),
        }
        for sent_key, api_keys in field_map.items():
            sent_val = params_sent.get(sent_key)
            read_val = next(
                (matched[k] for k in api_keys if k in matched), None
            )
            if sent_val is not None and read_val is not None:
                if str(sent_val) != str(read_val):
                    changed[sent_key] = {"before": None, "after": read_val}
                else:
                    unchanged.append(sent_key)

        return ReadbackDiff(changed=changed, unchanged=unchanged)

    def _readback_parameter(
        self,
        spec: _OperationSpec,
        device_sn: str,
        family: DeviceFamily,
        params_sent: dict[str, Any],
    ) -> ReadbackDiff:
        """Best-effort readback for min_write_parameter operations.

        Growatt OpenAPI V1 does not expose individual parameter read endpoints
        for most config parameters.  We record the sent value and note that
        direct verification is unavailable.
        """
        assert spec.param_spec is not None  # noqa: S101
        return ReadbackDiff(
            readback_failed=True,
            readback_error=(
                f"Direct readback of parameter {spec.param_spec.parameter_id!r} "
                "is not available via Growatt OpenAPI V1. "
                "The write was dispatched successfully — verify via GET /config."
            ),
        )


# ── Parameter validation helpers ──────────────────────────────────────────────


def _validate_time_segment_params(params: dict[str, Any]) -> list[str]:
    """Validate params for set_time_segment; return list of error strings."""
    errors: list[str] = []

    # segment
    seg = params.get("segment")
    if seg is None:
        errors.append("segment is required (integer 1–9).")
    else:
        try:
            seg_int = int(seg)
            if not (1 <= seg_int <= 9):
                errors.append(f"segment must be 1–9, got {seg_int}.")
        except (TypeError, ValueError):
            errors.append(f"segment must be an integer, got {seg!r}.")

    # mode
    mode = params.get("mode")
    if mode is None:
        errors.append("mode is required (0 = load-first, 1 = battery-first, 2 = grid-first).")
    else:
        try:
            mode_int = int(mode)
            if mode_int not in (0, 1, 2):
                errors.append(f"mode must be 0, 1, or 2, got {mode_int}.")
        except (TypeError, ValueError):
            errors.append(f"mode must be an integer (0–2), got {mode!r}.")

    # start_time / end_time
    for key in ("start_time", "end_time"):
        val = params.get(key)
        if val is None:
            errors.append(f"{key} is required (HH:MM format).")
        elif not _is_valid_hhmm(str(val)):
            errors.append(f"{key} must be in HH:MM format (00:00–23:59), got {val!r}.")

    return errors


def _validate_parameter_params(
    spec: _ParamSpec, params: dict[str, Any]
) -> list[str]:
    """Validate params for a min_write_parameter operation; return list of error strings."""
    errors: list[str] = []
    val = params.get(spec.value_key)

    if val is None:
        errors.append(f"'{spec.value_key}' is required.")
        return errors

    if spec.is_bool:
        if not isinstance(val, bool):
            errors.append(
                f"'{spec.value_key}' must be a boolean (true/false), got {val!r}."
            )
        return errors

    # Numeric
    try:
        num = float(val)
    except (TypeError, ValueError):
        errors.append(f"'{spec.value_key}' must be a number, got {val!r}.")
        return errors

    if spec.min_val is not None and num < spec.min_val:
        errors.append(
            f"'{spec.value_key}' must be ≥ {spec.min_val}, got {num}."
        )
    if spec.max_val is not None and num > spec.max_val:
        errors.append(
            f"'{spec.value_key}' must be ≤ {spec.max_val}, got {num}."
        )

    return errors


def _hhmm_to_hour_minute(s: str) -> tuple[int, int]:
    """Parse HH:MM into hour and minute (same rules as _is_valid_hhmm)."""
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time {s!r}")
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time {s!r}")
    return h, m


def _is_valid_hhmm(s: str) -> bool:
    """Return True if *s* matches HH:MM with valid hour (0–23) and minute (0–59)."""
    parts = s.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def _is_api_success(response: dict[str, Any] | None) -> bool:
    """Heuristically determine whether the Growatt API returned a success result.

    growattServer typically uses result_code == "1" for success, but some
    endpoints return {"result": 1} or {"result": "success"}.
    Legacy tcpSet.do JSON often exposes a top-level ``success`` boolean.
    """
    if not response:
        return False
    if "success" in response:
        return bool(response["success"])
    # Most common pattern from growattServer OpenApiV1
    code = response.get("result_code") or response.get("resultCode")
    if code is not None:
        return str(code) == "1"
    result = response.get("result")
    if result is not None:
        return result in (1, "1", "success", True)
    # Fallback: non-empty response with no explicit failure indicator → assume ok
    return bool(response)


def _extract_api_error(response: dict[str, Any] | None) -> str:
    """Extract a human-readable error message from an API failure response."""
    if not response:
        return "Empty response from Growatt Cloud API."
    msg = (
        response.get("result_msg")
        or response.get("resultMsg")
        or response.get("msg")
        or response.get("error")
        or response.get("message")
    )
    if msg:
        return str(msg)
    code = response.get("result_code") or response.get("resultCode") or response.get("result")
    return f"API returned failure code: {code}"
