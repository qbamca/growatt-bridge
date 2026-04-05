"""FastAPI application: lifespan, CORS, dependency wiring, and route registration."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .client import GrowattClient, build_client_from_settings
from .config import Settings
from .safety import SafetyLayer

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _configure_logging(level_name: str) -> None:
    """Apply root log level from settings (overrides import-time basicConfig)."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Initialise shared state on startup; clean up on shutdown."""
    try:
        settings = Settings()  # type: ignore[call-arg]  # env-driven
    except ValidationError as exc:
        logger.error(
            "Configuration failed (e.g. missing GROWATT_API_TOKEN). "
            "Set env vars or mount a .env in the process working directory. Details: %s",
            exc,
        )
        raise
    _configure_logging(settings.bridge_log_level)
    client = build_client_from_settings(settings)
    safety = SafetyLayer(settings, client)

    app.state.settings = settings
    app.state.client = client
    app.state.safety = safety

    logger.info(
        "growatt-bridge started. readonly=%s server=%s log_level=%s",
        settings.bridge_readonly,
        settings.growatt_server_url,
        settings.bridge_log_level,
    )
    yield
    logger.info("growatt-bridge shutting down.")


def create_app() -> FastAPI:
    """Construct and return the FastAPI application."""
    app = FastAPI(
        title="growatt-bridge",
        description=(
            "HTTP bridge service wrapping Growatt OpenAPI V1 with safety layer. "
            "All writes are disabled by default (BRIDGE_READONLY=true)."
        ),
        version="0.2.0",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Register routers
    from .routes.health import router as health_router
    from .routes.plants import router as plants_router
    from .routes.devices import router as devices_router
    from .routes.telemetry import router as telemetry_router
    from .routes.config_read import router as config_router
    from .routes.commands import router as commands_router
    from .routes.write_operations import router as write_operations_router

    app.include_router(health_router)
    app.include_router(plants_router)
    app.include_router(devices_router)
    app.include_router(telemetry_router)
    app.include_router(config_router)
    app.include_router(commands_router)
    app.include_router(write_operations_router)

    return app


app = create_app()
