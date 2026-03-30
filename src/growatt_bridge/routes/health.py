"""GET /health and GET /info endpoints."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..connectivity import growatt_host_reachable

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
    """Return process status and Growatt Cloud **host** reachability.

    Performs an unauthenticated HTTPS GET to ``GROWATT_SERVER_URL`` (root path).
    This checks DNS/TLS/connectivity only — it does **not** call the OpenAPI or
    verify the token (avoids burning API rate limits on container health checks).
    """
    settings = request.app.state.settings
    cloud_reachable, cloud_error = growatt_host_reachable(settings.growatt_server_url)
    if not cloud_reachable:
        logger.warning("Growatt host reachability check failed: %s", cloud_error)

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
        pkg_version = "0.2.0"

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
