#!/usr/bin/env python3
"""Explore: POST newTwoLoginAPI.do (Shine web portal login).

Authenticates with GROWATT_WEB_USERNAME / GROWATT_WEB_PASSWORD and saves
the full response for analysis. No writes are performed.

Saved fields of interest:
  response.body.back.success       -- bool, whether login succeeded
  response.body.back.user.*        -- user profile, timezone, serverUrl
  response.body.back.data[]        -- plant list returned on login
  response.cookies                 -- session cookies set by the server
  response.headers.Set-Cookie      -- raw cookie header (incl. Max-Age if present)

Usage:
    python scripts/explore/probe_login.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
sys.path.insert(0, str(_HERE))   # so `_base` is importable when run as a script
sys.path.insert(0, str(_SRC))    # so `growattServer` and bridge modules are importable

import os

from growattServer import hash_password  # type: ignore[import-untyped]

from _base import build_session, fail, info, ok, require_env, save_response

_PROBE_NAME = "login"

# Fields anywhere in the response body that contain sensitive data
_REDACT = {"password", "token"}


def probe() -> int:
    env = require_env("GROWATT_WEB_USERNAME", "GROWATT_WEB_PASSWORD")
    base_url = os.environ.get("GROWATT_WEB_BASE_URL", "https://server.growatt.com/")

    session, base = build_session(base_url)
    url = f"{base}newTwoLoginAPI.do"

    print(f"\nProbe : {_PROBE_NAME}")
    print(f"URL   : {url}")
    print(f"User  : {env['GROWATT_WEB_USERNAME']}")

    pw_hashed = hash_password(env["GROWATT_WEB_PASSWORD"])
    resp = session.post(url, data={"userName": env["GROWATT_WEB_USERNAME"], "password": pw_hashed})

    info(f"HTTP {resp.status_code}  ({resp.elapsed.total_seconds() * 1000:.0f} ms)")

    out = save_response(_PROBE_NAME, resp, redact_keys=list(_REDACT))
    info(f"Saved → {out}")

    try:
        back = resp.json().get("back", {})
    except Exception as exc:
        fail(f"Could not parse response as JSON: {exc}")
        return 1

    if not back.get("success"):
        error_msg = back.get("error") or back.get("msg") or "(no message)"
        error_code = back.get("msg", "")
        fail(f"Login failed [code={error_code}]: {error_msg}")
        return 1

    user = back.get("user", {})
    ok("Login succeeded")
    info(f"User ID      : {user.get('id')}")
    info(f"Account name : {user.get('accountName')}")
    info(f"Timezone     : {user.get('timeZone')}")
    info(f"Server URL   : {user.get('serverUrl')}")
    info(f"Right level  : {user.get('rightlevel')}")

    plants = back.get("data") or []
    info(f"Plants in response: {len(plants)}")
    for p in plants:
        info(f"  plant_id={p.get('plantId') or p.get('plant_id')}  name={p.get('plantName')}")

    cookies = dict(session.cookies)
    info(f"Session cookies: {list(cookies.keys())}")

    # Note Set-Cookie headers for TTL/Max-Age analysis
    set_cookie_headers = resp.headers.get("Set-Cookie", "")
    if set_cookie_headers:
        info(f"Set-Cookie     : {set_cookie_headers}")

    return 0


if __name__ == "__main__":
    sys.exit(probe())
