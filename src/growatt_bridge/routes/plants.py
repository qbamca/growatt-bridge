"""Plant read routes: GET /api/v1/plants and GET /api/v1/plants/{plant_id}."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..models import PlantDetail, PlantSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plants", tags=["plants"])


# ── Normalization helpers ──────────────────────────────────────────────────────


def _plant_id_from_raw(raw: dict[str, Any]) -> str:
    """Extract plant ID from a raw Growatt API dict, trying multiple key names."""
    return str(
        raw.get("plant_id")
        or raw.get("plantId")
        or raw.get("id")
        or ""
    )


def _float_or_none(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _normalize_plant_summary(raw: dict[str, Any]) -> PlantSummary:
    return PlantSummary(
        plant_id=_plant_id_from_raw(raw),
        plant_name=raw.get("plant_name") or raw.get("plantName") or raw.get("name"),
        total_power=_float_or_none(
            raw.get("currentPower") or raw.get("total_power") or raw.get("totalPower")
        ),
        status=str(raw.get("status")) if raw.get("status") is not None else None,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[PlantSummary], summary="List all plants")
async def list_plants(request: Request) -> list[PlantSummary]:
    """Return all plants accessible by the configured API token."""
    client = request.app.state.client
    try:
        plants = client.plant_list()
    except Exception as exc:  # noqa: BLE001
        logger.error("plant_list failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Growatt Cloud error: {exc}") from exc
    return [_normalize_plant_summary(p) for p in plants]


@router.get("/{plant_id}", response_model=PlantDetail, summary="Get plant details")
async def get_plant(plant_id: str, request: Request) -> PlantDetail:
    """Return detailed information for a single plant by ID."""
    client = request.app.state.client
    try:
        raw = client.plant_details(plant_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("plant_details(%s) failed: %s", plant_id, exc)
        raise HTTPException(status_code=502, detail=f"Growatt Cloud error: {exc}") from exc

    if not raw:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id!r} not found.")

    summary = _normalize_plant_summary(raw)
    # plant_id from the URL is authoritative if extraction fails
    resolved_id = summary.plant_id or plant_id

    return PlantDetail(
        plant_id=resolved_id,
        plant_name=summary.plant_name,
        total_power=summary.total_power,
        status=summary.status,
        raw=raw,
    )
