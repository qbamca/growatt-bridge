"""GET /health and GET /info endpoints."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    cloud_reachable: bool
    cloud_error: str | None = None


class InfoResponse(BaseModel):
    version: str
    readonly: bool
    allowed_write_operations: list[str]
    default_device_sn: str | None = None
    default_plant_id: str | None = None


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health(request: Request) -> HealthResponse:
    """Return service status and Growatt Cloud reachability.

    Attempts a lightweight ``plant_list`` call to confirm the token is valid
    and the Growatt Cloud endpoint is reachable.  Degraded status indicates
    a connectivity or authentication problem.
    """
    client = request.app.state.client
    cloud_reachable = True
    cloud_error: str | None = None
    try:
        client.plant_list()
    except Exception as exc:  # noqa: BLE001
        cloud_reachable = False
        cloud_error = str(exc)
        logger.warning("Cloud reachability check failed: %s", exc)

    return HealthResponse(
        status="ok" if cloud_reachable else "degraded",
        cloud_reachable=cloud_reachable,
        cloud_error=cloud_error,
    )


@router.get("/info", response_model=InfoResponse, summary="Bridge configuration summary")
async def info(request: Request) -> InfoResponse:
    """Return bridge version, readonly status, and allowed write operations."""
    settings = request.app.state.settings

    try:
        pkg_version = version("growatt-bridge")
    except PackageNotFoundError:
        pkg_version = "0.1.0"

    try:
        allowed_ops = settings.parsed_write_allowlist()
    except ValueError:
        allowed_ops = []

    return InfoResponse(
        version=pkg_version,
        readonly=settings.bridge_readonly,
        allowed_write_operations=allowed_ops,
        default_device_sn=settings.growatt_device_sn,
        default_plant_id=settings.growatt_plant_id,
    )
