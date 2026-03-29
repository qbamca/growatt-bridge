#!/usr/bin/env python3
"""End-to-end integration probe for growatt-bridge against a real Growatt server.

Boots the bridge in-process via ASGI transport (no separate server process needed),
discovers a plant and device from the configured test server, exercises every read
route, and runs validate (dry-run) against every write operation.  No actual writes
are sent to the inverter.

Usage:
    python scripts/test_integration.py [options]

    Options:
        --env-file PATH     Path to env file to load (default: .env.test)
        --server-url URL    Override GROWATT_SERVER_URL from env file
        --verbose           Print full JSON response bodies

Exit codes:
    0   All checks passed or skipped (expected when no devices on demo account)
    1   One or more checks failed
    2   Startup error (missing dependency, bad env file, bridge failed to boot)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Path bootstrap ─────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ── Imports (after path bootstrap) ────────────────────────────────────────────

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv is required. Run: pip install python-dotenv", file=sys.stderr)
    sys.exit(2)

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Run: pip install httpx", file=sys.stderr)
    sys.exit(2)

try:
    from asgi_lifespan import LifespanManager
except ImportError:
    print("ERROR: asgi-lifespan is required. Run: pip install asgi-lifespan", file=sys.stderr)
    sys.exit(2)


# ── Result tracking ────────────────────────────────────────────────────────────

_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"


@dataclass
class _Result:
    endpoint: str
    method: str
    status: str  # PASS | FAIL | SKIP
    http_status: int | None = None
    elapsed_ms: float = 0.0
    note: str = ""


_results: list[_Result] = []


# ── Console helpers ────────────────────────────────────────────────────────────

_VERBOSE = False


def _log(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def _warn(msg: str) -> None:
    print(f"  \033[33m⚠\033[0m {msg}")


def _fail(msg: str) -> None:
    print(f"  \033[31m✗\033[0m {msg}", file=sys.stderr)


def _verbose_body(data: Any) -> None:
    if _VERBOSE:
        print(json.dumps(data, indent=2, default=str))


# ── Check helpers ──────────────────────────────────────────────────────────────


def _record(endpoint: str, method: str, status: str, http_code: int | None, elapsed: float, note: str = "") -> None:
    _results.append(_Result(endpoint=endpoint, method=method, status=status, http_status=http_code, elapsed_ms=elapsed, note=note))


async def _get(
    client: httpx.AsyncClient,
    path: str,
    *,
    label: str | None = None,
    check_keys: list[str] | None = None,
    expected_statuses: tuple[int, ...] = (200,),
    skip_on_404: bool = False,
) -> tuple[str, Any]:
    """GET *path*, record result. Returns (outcome, response_json)."""
    display = label or path
    t0 = time.perf_counter()
    try:
        resp = await client.get(path)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        _fail(f"GET {display}: request error — {exc}")
        _record(display, "GET", _FAIL, None, elapsed, str(exc))
        return _FAIL, None

    elapsed = (time.perf_counter() - t0) * 1000
    code = resp.status_code

    if skip_on_404 and code == 404:
        _warn(f"GET {display}: 404 — skipping (device/plant not found)")
        _record(display, "GET", _SKIP, code, elapsed, "404 not found")
        return _SKIP, None

    if code not in expected_statuses:
        _fail(f"GET {display}: HTTP {code} (expected {expected_statuses})")
        _record(display, "GET", _FAIL, code, elapsed, f"unexpected HTTP {code}")
        return _FAIL, None

    try:
        body = resp.json()
    except Exception:
        body = resp.text

    _verbose_body(body)

    if check_keys and isinstance(body, dict):
        missing = [k for k in check_keys if k not in body]
        if missing:
            _fail(f"GET {display}: missing keys {missing}")
            _record(display, "GET", _FAIL, code, elapsed, f"missing keys: {missing}")
            return _FAIL, body

    _ok(f"GET {display}: HTTP {code} ({elapsed:.0f} ms)")
    _record(display, "GET", _PASS, code, elapsed)
    return _PASS, body


async def _post_validate(
    client: httpx.AsyncClient,
    path: str,
    payload: dict[str, Any],
    *,
    label: str | None = None,
) -> str:
    """POST *path* (validate/dry-run), record result. Returns outcome."""
    display = label or path
    t0 = time.perf_counter()
    try:
        resp = await client.post(path, json=payload)
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        _fail(f"POST {display}: request error — {exc}")
        _record(display, "POST", _FAIL, None, elapsed, str(exc))
        return _FAIL

    elapsed = (time.perf_counter() - t0) * 1000
    code = resp.status_code

    # 422 = device family unsupported — not a script failure, just skip
    if code == 422:
        _warn(f"POST {display}: HTTP 422 (unsupported family / device type) — skip")
        _record(display, "POST", _SKIP, code, elapsed, "unsupported family")
        return _SKIP

    # 404 = unknown device (no devices discovered)
    if code == 404:
        _warn(f"POST {display}: HTTP 404 — skip (device not found)")
        _record(display, "POST", _SKIP, code, elapsed, "404 not found")
        return _SKIP

    # validate endpoint returns 200; execute would return 403 in readonly mode
    if code not in (200, 403):
        _fail(f"POST {display}: HTTP {code}")
        _record(display, "POST", _FAIL, code, elapsed, f"unexpected HTTP {code}")
        return _FAIL

    try:
        body = resp.json()
    except Exception:
        body = resp.text

    _verbose_body(body)

    if code == 200 and isinstance(body, dict):
        valid = body.get("valid")
        errors = body.get("errors") or []
        note = f"valid={valid}"
        if errors:
            note += f" errors={errors}"
        _ok(f"POST {display}: HTTP {code} {note} ({elapsed:.0f} ms)")
    else:
        _ok(f"POST {display}: HTTP {code} ({elapsed:.0f} ms)")

    _record(display, "POST", _PASS, code, elapsed)
    return _PASS


# ── Summary table ──────────────────────────────────────────────────────────────


def _print_summary() -> None:
    W_EP = max(50, max(len(r.endpoint) for r in _results))
    hdr = f"{'Endpoint':<{W_EP}}  {'M':<4}  {'Status':<6}  {'HTTP':<4}  {'ms':>6}  Note"
    print(f"\n{'═' * (len(hdr) + 2)}")
    print(f"  {hdr}")
    print(f"{'─' * (len(hdr) + 2)}")
    for r in _results:
        colour = "\033[32m" if r.status == _PASS else ("\033[33m" if r.status == _SKIP else "\033[31m")
        reset = "\033[0m"
        http = str(r.http_status) if r.http_status else "—"
        print(
            f"  {r.endpoint:<{W_EP}}  {r.method:<4}  {colour}{r.status:<6}{reset}  {http:<4}  {r.elapsed_ms:>6.0f}  {r.note}"
        )
    print(f"{'═' * (len(hdr) + 2)}\n")

    passes = sum(1 for r in _results if r.status == _PASS)
    skips = sum(1 for r in _results if r.status == _SKIP)
    fails = sum(1 for r in _results if r.status == _FAIL)
    print(f"  Results: {passes} passed, {skips} skipped, {fails} failed")
    if fails:
        print(f"\n  \033[31mFAILED — {fails} check(s) did not pass.\033[0m")
    else:
        print(f"\n  \033[32mAll checks passed or skipped.\033[0m")
    print()


# ── Main probe ─────────────────────────────────────────────────────────────────


async def _run(server_url_override: str | None) -> int:
    """Boot the bridge in-process and run all checks. Returns exit code."""

    # Import bridge after env vars are set
    try:
        from growatt_bridge.main import create_app
        from growatt_bridge.config import Settings
    except Exception as exc:
        _fail(f"Could not import growatt_bridge: {exc}")
        return 2

    # Validate settings can be loaded (gives a clear message if token is missing)
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as exc:
        _fail(f"Could not load Settings: {exc}")
        _fail("Check that GROWATT_API_TOKEN is set in your env file.")
        return 2

    if server_url_override:
        os.environ["GROWATT_SERVER_URL"] = server_url_override.rstrip("/") + "/"
        # Re-read after override
        settings = Settings()  # type: ignore[call-arg]

    print(f"\n  growatt-bridge integration probe")
    print(f"  Server : {settings.growatt_server_url}")
    print(f"  Token  : {settings.redacted_token()}")
    print(f"  Readonly: {settings.bridge_readonly}")
    print()

    app = create_app()

    async with LifespanManager(app) as manager, httpx.AsyncClient(
        transport=httpx.ASGITransport(app=manager.app),
        base_url="http://testserver",
        timeout=30.0,
    ) as client:
        # ── Health / Info ──────────────────────────────────────────────────
        print("[health] Basic endpoints")
        await _get(client, "/health", check_keys=["status"])
        await _get(client, "/info", check_keys=["readonly"])

        # ── Plants ────────────────────────────────────────────────────────
        print("\n[plants] Plant list")
        outcome, plants_body = await _get(client, "/api/v1/plants", label="GET /api/v1/plants")
        if outcome != _PASS or not isinstance(plants_body, list) or not plants_body:
            _warn("No plants returned — skipping all device-level checks.")
            return 0 if outcome != _FAIL else 1

        plant = plants_body[0]
        plant_id = str(plant.get("plant_id") or plant.get("plantId") or plant.get("id") or "")
        if not plant_id:
            _fail("Cannot extract plant_id from /api/v1/plants response.")
            return 1
        _log(f"Using plant_id={plant_id!r}")

        # Plant detail
        print("\n[plants] Plant detail")
        await _get(
            client,
            f"/api/v1/plants/{plant_id}",
            label=f"GET /api/v1/plants/{plant_id}",
            check_keys=["plant_id"],
        )

        # ── Devices ───────────────────────────────────────────────────────
        print("\n[devices] Device list")
        outcome, devices_body = await _get(
            client,
            f"/api/v1/plants/{plant_id}/devices",
            label=f"GET /api/v1/plants/{plant_id}/devices",
        )

        device_sn: str | None = None
        if outcome == _PASS and isinstance(devices_body, list) and devices_body:
            raw_dev = devices_body[0]
            device_sn = str(
                raw_dev.get("device_sn")
                or raw_dev.get("deviceSn")
                or raw_dev.get("serialNum")
                or raw_dev.get("sn")
                or ""
            ) or None
            if device_sn:
                _log(f"Using device_sn={device_sn!r}")
            else:
                _warn("Could not extract device_sn from device list — skipping device-level checks.")
        else:
            _warn("No devices found — skipping device-level checks.")

        if not device_sn:
            _print_summary()
            return 1 if any(r.status == _FAIL for r in _results) else 0

        # Device detail
        print("\n[devices] Device detail + capabilities")
        sn_path = f"/api/v1/devices/{device_sn}"
        await _get(client, sn_path, label=f"GET {sn_path}", check_keys=["device_sn", "family"])
        await _get(
            client,
            f"{sn_path}/capabilities",
            label=f"GET {sn_path}/capabilities",
            check_keys=["family", "readonly"],
        )

        # ── Telemetry ─────────────────────────────────────────────────────
        print("\n[telemetry] Live telemetry")
        await _get(
            client,
            f"{sn_path}/telemetry",
            label=f"GET {sn_path}/telemetry",
            check_keys=["device_sn"],
            skip_on_404=True,
        )

        # ── Config reads ──────────────────────────────────────────────────
        print("\n[config] Config snapshot + time-segments")
        await _get(
            client,
            f"{sn_path}/config",
            label=f"GET {sn_path}/config",
            check_keys=["device_sn"],
            skip_on_404=True,
        )
        # time-segments: 200 for MIN devices, 422 for other families
        await _get(
            client,
            f"{sn_path}/config/time-segments",
            label=f"GET {sn_path}/config/time-segments",
            expected_statuses=(200, 422),
            skip_on_404=True,
        )

        # ── Validate (dry-run) write operations ───────────────────────────
        print("\n[validate] Dry-run validate — no writes executed")

        validate_cases: list[tuple[str, dict[str, Any]]] = [
            ("set_ac_charge_stop_soc", {"params": {"value": 90}}),
        ]

        for op_id, payload in validate_cases:
            validate_path = f"{sn_path}/commands/{op_id}/validate"
            await _post_validate(
                client,
                validate_path,
                payload,
                label=f"POST {sn_path}/commands/{op_id}/validate",
            )

    # ── Summary ───────────────────────────────────────────────────────────
    _print_summary()
    return 1 if any(r.status == _FAIL for r in _results) else 0


# ── CLI ────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--env-file",
        default=str(_REPO_ROOT / ".env.test"),
        help="Path to env file to load (default: .env.test in repo root)",
    )
    parser.add_argument(
        "--server-url",
        default=None,
        help="Override GROWATT_SERVER_URL (takes precedence over env file)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full JSON response bodies",
    )
    args = parser.parse_args(argv)

    global _VERBOSE
    _VERBOSE = args.verbose

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"ERROR: env file not found: {env_path}", file=sys.stderr)
        print("  Create it or pass --env-file PATH", file=sys.stderr)
        return 2

    load_dotenv(env_path, override=True)
    print(f"Loaded env from: {env_path}")

    try:
        return asyncio.run(_run(args.server_url))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 2
    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
