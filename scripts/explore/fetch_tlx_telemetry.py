#!/usr/bin/env python3
"""Explore: TLX telemetry — save JSON for data-model / plan analysis.

**Primary (programmatic web session)** — ``POST newTlxApi.do`` with the same
``newTwoLoginAPI`` session as ``tcpSet.do`` / ``readAllMinParam``:

* ``op=getSystemStatus_KW`` — live power / SoC / voltages (maps conceptually to portal ``getTLXStatusData_bdc``).
* ``op=getEnergyOverview`` — today / cumulative energy totals (maps conceptually to ``getTLXTotalData_bdc``).

**Optional (browser parity)** — POST ``/panel/tlx/getTLXStatusData_bdc`` and ``getTLXTotalData_bdc``
as in the Shine UI. These routes may return **302 → errorNoLogin** unless you paste a full browser
``Cookie`` header (set env ``GROWATT_BROWSER_COOKIE``).

Artifacts under ``audit/explore/``:

* ``<ts>_tlx_newTlxApi_system_status.json``
* ``<ts>_tlx_newTlxApi_energy_overview.json``
* ``<ts>_tlx_status_data_bdc.json`` (panel; may be redirect/HTML without browser cookies)
* ``<ts>_tlx_total_data_bdc.json``

Usage::

    python scripts/explore/fetch_tlx_telemetry.py

Environment (repo ``.env``):

    GROWATT_WEB_USERNAME   GROWATT_WEB_PASSWORD
    GROWATT_PLANT_ID       GROWATT_DEVICE_SN
    GROWATT_WEB_BASE_URL   optional

    GROWATT_BROWSER_COOKIE optional — full ``Cookie`` header value from DevTools (Application → Cookies
    for ``server.growatt.com``), to unlock ``/panel/tlx/…_bdc`` JSON when needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_SRC))

from growatt_bridge.legacy_shine_web import (  # noqa: E402
    LegacyShineWebClient,
    LegacyShineWebError,
)

from _base import fail, info, ok, require_env, save_response  # noqa: E402

_REDACT = {"password", "token"}


def _apply_cookie_header(session: object, header: str, domain: str) -> None:
    """Merge ``Cookie`` header pairs into ``requests.Session`` (browser export)."""
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if name:
            session.cookies.set(name, value, domain=domain, path="/")


def _envelope_extra_panel(resp: object) -> dict:
    """Metadata when panel response is not JSON (redirect / login HTML)."""
    r = resp
    extra: dict = {}
    code = getattr(r, "status_code", 0)
    if getattr(r, "is_redirect", False) or 300 <= code < 400:
        extra["panel_auth"] = "redirect"
        extra["location"] = r.headers.get("Location")
    body = getattr(r, "text", "") or ""
    if "errorNoLogin" in body or "dumpLogin" in body or "Not Login" in body:
        extra["panel_auth"] = extra.get("panel_auth") or "login_html"
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "json" not in ctype and body.lstrip().startswith("<!"):
        extra["panel_auth"] = extra.get("panel_auth") or "html_not_json"
    return extra


def _looks_like_telemetry_json(resp: object) -> bool:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "json" in ctype:
        return True
    t = (resp.text or "").lstrip()
    return bool(t.startswith("{") or t.startswith("["))


def main() -> int:
    env = require_env(
        "GROWATT_WEB_USERNAME",
        "GROWATT_WEB_PASSWORD",
        "GROWATT_PLANT_ID",
        "GROWATT_DEVICE_SN",
    )
    base_url = os.environ.get("GROWATT_WEB_BASE_URL", "https://server.growatt.com/")
    plant_id = env["GROWATT_PLANT_ID"]
    serial = env["GROWATT_DEVICE_SN"]
    browser_cookie = (os.environ.get("GROWATT_BROWSER_COOKIE") or "").strip()

    print("\nProbe : TLX telemetry (newTlxApi + optional panel/tlx/*_bdc)")
    print(f"Base  : {base_url}")
    print(f"Plant : {plant_id}")
    print(f"SN    : {serial}")
    if browser_cookie:
        info("GROWATT_BROWSER_COOKIE is set — merging into session for panel XHR")

    client = LegacyShineWebClient(
        base_url,
        env["GROWATT_WEB_USERNAME"],
        env["GROWATT_WEB_PASSWORD"],
    )
    host = urlparse(client.base_url).hostname or "server.growatt.com"

    paths: list[Path] = []
    try:
        # Log in first; applying GROWATT_BROWSER_COOKIE only after login avoids newTwoLoginAPI
        # overwriting the browser export before panel XHR.
        client.ensure_logged_in()
        if browser_cookie:
            _apply_cookie_header(client._session, browser_cookie, host)

        # ── newTlxApi.do (works with newTwoLoginAPI + plant/device cookies) ──
        r_sys = client.new_tlx_api_post_raw(
            "getSystemStatus_KW",
            {"plantId": plant_id, "id": serial},
            plant_id=plant_id,
            serial_num=serial,
        )
        info(
            f"newTlxApi op=getSystemStatus_KW → HTTP {r_sys.status_code} "
            f"({r_sys.elapsed.total_seconds() * 1000:.0f} ms)"
        )
        paths.append(
            save_response(
                "tlx_newTlxApi_system_status",
                r_sys,
                redact_keys=list(_REDACT),
            )
        )
        info(f"Saved → {paths[-1]}")

        r_e = client.new_tlx_api_post_raw(
            "getEnergyOverview",
            {"plantId": plant_id, "id": serial},
            plant_id=plant_id,
            serial_num=serial,
        )
        info(
            f"newTlxApi op=getEnergyOverview → HTTP {r_e.status_code} "
            f"({r_e.elapsed.total_seconds() * 1000:.0f} ms)"
        )
        paths.append(
            save_response(
                "tlx_newTlxApi_energy_overview",
                r_e,
                redact_keys=list(_REDACT),
            )
        )
        info(f"Saved → {paths[-1]}")

        if r_sys.status_code >= 400 or r_e.status_code >= 400:
            fail("newTlxApi request failed (HTTP >= 400)")
            return 1
        if not _looks_like_telemetry_json(r_sys) or not _looks_like_telemetry_json(r_e):
            fail("newTlxApi response did not look like JSON — check artifacts")
            return 1

        # ── Panel XHR (may 302 without full browser cookies) ──
        r1 = client.get_tlx_status_data_bdc_raw(plant_id, serial, allow_redirects=False)
        extra1 = _envelope_extra_panel(r1)
        paths.append(
            save_response(
                "tlx_status_data_bdc",
                r1,
                redact_keys=list(_REDACT),
                extra=extra1 or None,
            )
        )
        info(f"getTLXStatusData_bdc (no redirect follow) → HTTP {r1.status_code}  Saved → {paths[-1]}")

        r2 = client.get_tlx_total_data_bdc_raw(plant_id, serial, allow_redirects=False)
        extra2 = _envelope_extra_panel(r2)
        paths.append(
            save_response(
                "tlx_total_data_bdc",
                r2,
                redact_keys=list(_REDACT),
                extra=extra2 or None,
            )
        )
        info(f"getTLXTotalData_bdc (no redirect follow) → HTTP {r2.status_code}  Saved → {paths[-1]}")

        if browser_cookie:
            info("Panel POSTs with redirects allowed (browser cookie path)")
            r1b = client.get_tlx_status_data_bdc_raw(plant_id, serial, allow_redirects=True)
            paths.append(
                save_response(
                    "tlx_status_data_bdc_follow",
                    r1b,
                    redact_keys=list(_REDACT),
                    extra=_envelope_extra_panel(r1b) or None,
                )
            )
            r2b = client.get_tlx_total_data_bdc_raw(plant_id, serial, allow_redirects=True)
            paths.append(
                save_response(
                    "tlx_total_data_bdc_follow",
                    r2b,
                    redact_keys=list(_REDACT),
                    extra=_envelope_extra_panel(r2b) or None,
                )
            )
            info(f"Saved follow redirects → …_tlx_status_data_bdc_follow.json, …_tlx_total_data_bdc_follow.json")

    except LegacyShineWebError as exc:
        fail(str(exc))
        return 1
    except OSError as exc:
        fail(str(exc))
        return 1

    ok("Telemetry artifacts saved (use newTlxApi JSON for schema; panel files document UI XHR / auth)")
    for p in paths:
        info(str(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
