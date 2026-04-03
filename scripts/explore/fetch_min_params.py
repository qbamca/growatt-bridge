#!/usr/bin/env python3
"""Explore: POST tcpSet.do (action=readAllMinParam) — full MIN inverter settings.

Logs in via Shine web (same as ``LegacyShineWebClient``), mirrors portal plant /
device cookies, then requests ``readAllMinParam`` for ``GROWATT_DEVICE_SN``.
Saves the raw HTTP response under ``audit/explore/`` for later parameter mapping.

Usage:
    python scripts/explore/fetch_min_params.py

Environment (see repo ``.env``):
    GROWATT_WEB_USERNAME   GROWATT_WEB_PASSWORD
    GROWATT_PLANT_ID       GROWATT_DEVICE_SN
    GROWATT_WEB_BASE_URL   optional, default https://server.growatt.com/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_SRC))

from growatt_bridge.legacy_shine_web import (  # noqa: E402
    LegacyShineWebClient,
    LegacyShineWebError,
)

from _base import fail, info, ok, require_env, save_response  # noqa: E402

_PROBE_NAME = "read_all_min_param"
_REDACT = {"password", "token"}


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

    print(f"\nProbe : {_PROBE_NAME}")
    print(f"Base  : {base_url}")
    print(f"Plant : {plant_id}")
    print(f"SN    : {serial}")

    client = LegacyShineWebClient(
        base_url,
        env["GROWATT_WEB_USERNAME"],
        env["GROWATT_WEB_PASSWORD"],
    )
    try:
        resp = client.read_all_min_param_raw(plant_id, serial)
    except LegacyShineWebError as exc:
        fail(str(exc))
        return 1

    info(f"HTTP {resp.status_code}  ({resp.elapsed.total_seconds() * 1000:.0f} ms)")
    out = save_response(_PROBE_NAME, resp, redact_keys=list(_REDACT))
    info(f"Saved → {out}")

    if resp.status_code >= 400:
        fail(f"Request failed with status {resp.status_code}")
        return 1

    ok("Response saved (map fields in a follow-up step)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
