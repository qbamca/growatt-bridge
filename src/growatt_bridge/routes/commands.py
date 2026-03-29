"""Write command routes.

Endpoints:
- POST /api/v1/devices/{device_sn}/commands/{operation_id}
      Execute a named write operation through the full safety pipeline.

- POST /api/v1/devices/{device_sn}/commands/{operation_id}/validate
      Dry-run: validate parameters without touching Growatt Cloud.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request, status

from ..client import DeviceFamily, GrowattClient, UnsupportedDeviceFamilyError
from ..config import Settings
from ..models import CommandRequest, CommandResponse, ValidateResponse
from ..safety import (
    OPERATION_REGISTRY,
    OperationValidationError,
    RateLimitError,
    SafetyLayer,
    UnknownOperationError,
    WriteNotPermittedError,
)
from .devices import _resolve_plant_id

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/devices/{device_sn}/commands",
    tags=["commands"],
)

# ── Shared helpers ─────────────────────────────────────────────────────────────


def _operation_not_found_response(operation_id: str) -> HTTPException:
    known = sorted(OPERATION_REGISTRY)
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"Unknown operation {operation_id!r}. "
            f"Valid operation IDs: {known}"
        ),
    )


# ── Execute route ──────────────────────────────────────────────────────────────


@router.post(
    "/{operation_id}",
    response_model=CommandResponse,
    summary="Execute a write command",
    responses={
        200: {"description": "Command dispatched (check success field for outcome)."},
        403: {"description": "Write blocked: readonly mode or operation not allowlisted."},
        404: {"description": "Unknown operation_id."},
        422: {"description": "Parameter validation failed or unsupported device family."},
        429: {"description": "Write rate limit exceeded."},
        502: {"description": "Growatt Cloud communication error."},
    },
)
async def execute_command(
    device_sn: str,
    operation_id: str,
    body: CommandRequest,
    request: Request,
    plant_id: str | None = Query(
        default=None,
        description="Plant ID containing this device. Defaults to GROWATT_PLANT_ID env var.",
    ),
) -> CommandResponse:
    """Execute *operation_id* on *device_sn* through the full safety pipeline.

    The bridge enforces readonly mode, the write allowlist, parameter range
    validation, write rate limiting, and post-write readback before returning.
    Every call (success or failure) is recorded in the append-only audit log.

    **This endpoint makes real changes to the inverter.** Always run the
    `/validate` dry-run first, and consult `docs/parameters/` for each
    operation's safety constraints.
    """
    client: GrowattClient = request.app.state.client
    settings: Settings = request.app.state.settings
    safety: SafetyLayer = request.app.state.safety

    # Reject unknown operations before touching the device
    if operation_id not in OPERATION_REGISTRY:
        raise _operation_not_found_response(operation_id)

    try:
        resolved_plant_id = await _resolve_plant_id(
            client, device_sn, settings, hint=plant_id
        )
        family = client.detect_device_family(device_sn, resolved_plant_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Failed to detect device family: {exc}",
        ) from exc

    try:
        response = safety.execute_write(
            operation_id=operation_id,
            device_sn=device_sn,
            family=family,
            params=body.params,
            plant_id=resolved_plant_id,
        )
    except WriteNotPermittedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except UnknownOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OperationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"errors": exc.errors},
        ) from exc
    except RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except UnsupportedDeviceFamilyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Unexpected error executing %r on %s: %s",
            operation_id,
            device_sn,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected error: {type(exc).__name__}: {exc}",
        ) from exc

    return response


# ── Validate (dry-run) route ───────────────────────────────────────────────────


@router.post(
    "/{operation_id}/validate",
    response_model=ValidateResponse,
    summary="Dry-run validate a write command",
    responses={
        200: {"description": "Validation result (check valid field)."},
        404: {"description": "Unknown operation_id."},
        502: {"description": "Growatt Cloud communication error (family detection)."},
    },
)
async def validate_command(
    device_sn: str,
    operation_id: str,
    body: CommandRequest,
    request: Request,
    plant_id: str | None = Query(
        default=None,
        description="Plant ID containing this device. Defaults to GROWATT_PLANT_ID env var.",
    ),
) -> ValidateResponse:
    """Validate *operation_id* parameters without executing the write.

    Checks:
    1. Readonly mode and allowlist (permission)
    2. Device family compatibility
    3. Parameter ranges and required fields

    The write rate limit is **not** checked — dry runs are free.
    No changes are made to the inverter or audit log.
    """
    client: GrowattClient = request.app.state.client
    settings: Settings = request.app.state.settings
    safety: SafetyLayer = request.app.state.safety

    if operation_id not in OPERATION_REGISTRY:
        raise _operation_not_found_response(operation_id)

    try:
        resolved_plant_id = await _resolve_plant_id(
            client, device_sn, settings, hint=plant_id
        )
        family = client.detect_device_family(device_sn, resolved_plant_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Failed to detect device family: {exc}",
        ) from exc

    valid, errors = safety.dry_run_validate(
        operation_id=operation_id,
        device_sn=device_sn,
        family=family,
        params=body.params,
        plant_id=resolved_plant_id,
    )

    return ValidateResponse(
        valid=valid,
        operation=operation_id,
        device_sn=device_sn,
        params=body.params,
        errors=errors,
    )
