"""Integration test fixtures — real Growatt Cloud + Shine legacy web, no mocks.

All tests in this package are skipped when required credentials are missing.
The repo-root ``.env`` is loaded at import time so local runs match the app.

**Legacy-only policy:** Integration tests require **Shine web portal credentials**
(``GROWATT_WEB_USERNAME`` / ``GROWATT_WEB_PASSWORD``) so ``GrowattClient`` attaches
``LegacyShineWebClient``. MIN **reads** (plants, devices, TLX detail, config) and
**writes** (tcpSet.do via ``bridge_legacy_web_min_writes=True``) then use the legacy
portal session. The OpenAPI token is still required to construct ``OpenApiV1`` (some
code paths and token auth); health checks do not call the OpenAPI.

The live_app_client fixture wires a real GrowattClient into a real FastAPI app
via ASGITransport so the full route → SafetyLayer → GrowattClient → Cloud chain
runs without spinning up an HTTP server.

Safety overrides applied for the test session:
- bridge_readonly = False
- bridge_legacy_web_min_writes = True (writes use tcpSet.do only)
- bridge_write_allowlist = all tested write operations
- bridge_rate_limit_writes = 20 (default 3 would block a 6-write test run)
- bridge_require_readback = True

IMPORTANT — mock isolation
--------------------------
tests/conftest.py installs a MagicMock for growattServer via sys.modules.setdefault()
so that unit tests never make real API calls.  That conftest is loaded by pytest
before this one (parent directory is always loaded first), which means by the time
we run, all growatt_bridge.* modules have already been imported with the mock baked in.

The block below removes the mock and reloads every affected module so that
integration tests use the real growattServer package.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ── Restore real growattServer before importing bridge modules ────────────────
# If the unit-test mock is in place, remove it together with all bridge modules
# that already imported it.  Subsequent imports will pick up the real package.
_mock = sys.modules.get("growattServer")
if isinstance(_mock, MagicMock):
    del sys.modules["growattServer"]
    for _key in [k for k in list(sys.modules) if k.startswith("growatt_bridge")]:
        del sys.modules[_key]

# ── Now import bridge modules — they will use the real growattServer ──────────

import os
from pathlib import Path

from dotenv import load_dotenv
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from growatt_bridge.client import build_client_from_settings
from growatt_bridge.config import Settings
from growatt_bridge.main import create_app
from growatt_bridge.safety import SafetyLayer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.is_file():
    load_dotenv(_ENV_FILE)

_WRITE_ALLOWLIST = "set_ac_charge_stop_soc,set_ac_charge_enable,set_on_grid_discharge_stop_soc,set_time_segment"


@pytest.fixture(scope="session")
def real_settings() -> Settings:
    if not os.environ.get("GROWATT_API_TOKEN"):
        pytest.skip("GROWATT_API_TOKEN not set — skipping integration tests")
    base = Settings()
    if not (base.growatt_web_username and base.growatt_web_password):
        pytest.skip(
            "Integration tests use legacy Shine web only: set GROWATT_WEB_USERNAME "
            "and GROWATT_WEB_PASSWORD (see docs for tcpSet / portal login)."
        )
    return base.model_copy(
        update={
            "bridge_readonly": False,
            "bridge_legacy_web_min_writes": True,
            "bridge_write_allowlist": _WRITE_ALLOWLIST,
            "bridge_rate_limit_writes": 20,
            "bridge_require_readback": True,
            "bridge_audit_log": Path("/tmp/growatt-integration-audit.jsonl"),
        }
    )


@pytest_asyncio.fixture(scope="session")
async def live_app_client(real_settings: Settings) -> AsyncClient:
    from growatt_bridge.client import GrowattClient

    client = build_client_from_settings(real_settings)
    assert isinstance(client, GrowattClient)
    assert client.legacy_shine_web is not None, (
        "integration expects LegacyShineWebClient (set web username/password)"
    )
    safety = SafetyLayer(real_settings, client)
    app = create_app()
    app.state.settings = real_settings
    app.state.client = client
    app.state.safety = safety
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def device_sn(real_settings: Settings) -> str:
    sn = real_settings.growatt_device_sn
    if not sn:
        pytest.skip("GROWATT_DEVICE_SN not set — skipping device-level integration tests")
    return sn


@pytest.fixture(scope="session")
def plant_id(real_settings: Settings) -> str | None:
    return real_settings.growatt_plant_id
