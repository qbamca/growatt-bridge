"""GET /api/v1/write-operations — static catalog of named write operations."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..config import Settings
from ..models import WriteOperationsCatalogResponse
from ..safety import build_write_operations_catalog

router = APIRouter(prefix="/api/v1", tags=["write-operations"])


@router.get(
    "/write-operations",
    response_model=WriteOperationsCatalogResponse,
    response_model_exclude_none=True,
    summary="List write operations and parameter schemas",
)
async def list_write_operations(
    request: Request,
    include_policy: bool = Query(
        False,
        description=(
            "If true, include currently_permitted per operation and server "
            "readonly / allowlist_parse_error from environment."
        ),
    ),
) -> WriteOperationsCatalogResponse:
    """Return every registered write operation with parameter metadata.

    This endpoint does not call Growatt Cloud. Use together with
    ``GET /api/v1/devices/{sn}/capabilities`` for device-family filtering.
    """
    settings: Settings = request.app.state.settings
    raw = build_write_operations_catalog(
        include_policy=include_policy,
        settings=settings if include_policy else None,
    )
    return WriteOperationsCatalogResponse.model_validate(raw)
