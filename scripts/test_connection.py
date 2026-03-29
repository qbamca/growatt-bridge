#!/usr/bin/env python3
"""Quick smoke test for real Growatt OpenAPI V1 credentials.

Authenticates with the token in GROWATT_API_TOKEN (loaded from .env),
walks the plant → device → telemetry hierarchy, and prints redacted JSON
for each response.  No writes are made.

Usage:
    python scripts/test_connection.py [--server-url URL]

Exit codes:
    0  All required calls succeeded (plant_list, device_list).
    1  Startup error (missing token, import failure).
    2  Required API call failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Resolve the repo root so this script can be run from any working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")

from growatt_bridge.config import Settings  # noqa: E402
from growatt_bridge.client import GrowattClient, DeviceFamily  # noqa: E402


# ── Output helpers ────────────────────────────────────────────────────────────


def _print_section(label: str, data: object) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(json.dumps(data, indent=2, default=str))


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠ {msg}", file=sys.stderr)


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server-url",
        default=None,
        help="Override Growatt server URL (default: from GROWATT_SERVER_URL or openapi.growatt.com)",
    )
    args = parser.parse_args(argv)

    # ── Load settings ─────────────────────────────────────────────────────────
    try:
        settings = Settings()  # type: ignore[call-arg]
    except Exception as exc:
        _fail(f"Could not load settings: {exc}")
        _fail("Set GROWATT_API_TOKEN in .env or the environment and try again.")
        return 1

    if args.server_url:
        server_url = args.server_url.rstrip("/") + "/"
    else:
        server_url = settings.growatt_server_url

    print(f"\ngrowatt-bridge smoke test")
    print(f"  Server : {server_url}")
    print(f"  Token  : {settings.redacted_token()}")

    # ── Build client ──────────────────────────────────────────────────────────
    client = GrowattClient(token=settings.growatt_api_token, server_url=server_url)
    _ok(f"Client constructed: {client!r}")

    # ── plant_list ────────────────────────────────────────────────────────────
    print("\n[1/4] plant_list")
    try:
        plants = client.plant_list()
        _print_section("plant_list response", plants)
        _ok(f"Found {len(plants)} plant(s)")
    except Exception as exc:
        _fail(f"plant_list failed: {exc}")
        return 2

    if not plants:
        _warn("No plants found — nothing more to test.")
        print("\nSmoke test complete (no plants).")
        return 0

    # Extract first plant ID
    plant = plants[0]
    plant_id = str(
        plant.get("plant_id") or plant.get("plantId") or plant.get("id") or ""
    )
    if not plant_id:
        _fail("Could not extract plant_id from plant_list response.")
        return 2

    _ok(f"Using plant_id={plant_id!r}")

    # ── plant_details ─────────────────────────────────────────────────────────
    print("\n[2/4] plant_details")
    try:
        details = client.plant_details(plant_id)
        _print_section(f"plant_details({plant_id!r})", details)
        _ok("plant_details OK")
    except Exception as exc:
        _warn(f"plant_details failed (non-fatal): {exc}")

    # ── device_list ───────────────────────────────────────────────────────────
    print("\n[3/4] device_list")
    try:
        devices = client.device_list(plant_id)
        _print_section(f"device_list({plant_id!r})", devices)
        _ok(f"Found {len(devices)} device(s)")
    except Exception as exc:
        _fail(f"device_list failed: {exc}")
        return 2

    if not devices:
        _warn("No devices found — skipping device-specific calls.")
        print("\nSmoke test complete (no devices).")
        return 0

    # Classify devices by family
    min_sn: str | None = None
    sph_sn: str | None = None
    device_families: dict[str, str] = {}

    for dev in devices:
        raw_type = dev.get("deviceType") or dev.get("type") or dev.get("device_type")
        sn = str(
            dev.get("device_sn")
            or dev.get("deviceSn")
            or dev.get("serialNum")
            or dev.get("sn")
            or ""
        )
        if not sn:
            continue

        try:
            dev_type = int(raw_type)
        except (TypeError, ValueError):
            dev_type = None

        if dev_type == 7:
            family = "MIN"
            min_sn = min_sn or sn
        elif dev_type == 5:
            family = "SPH"
            sph_sn = sph_sn or sn
        else:
            family = f"UNKNOWN(type={raw_type})"

        device_families[sn] = family
        _ok(f"Device {sn!r}: family={family}")

    # ── Telemetry reads ───────────────────────────────────────────────────────
    print("\n[4/4] Device telemetry reads")

    target_sn = min_sn or sph_sn
    if not target_sn:
        _warn("No MIN or SPH device found — skipping telemetry read.")
        print("\nSmoke test complete.")
        return 0

    family_enum = DeviceFamily.MIN if min_sn else DeviceFamily.SPH
    _ok(f"Testing telemetry for {target_sn!r} (family={family_enum.value})")

    for label, fn in _build_telemetry_calls(client, target_sn, family_enum):
        try:
            result = fn()
            _print_section(label, result)
            _ok(f"{label} OK")
        except Exception as exc:
            _warn(f"{label} failed (non-fatal): {exc}")

    # ── TOU segments (MIN only) ───────────────────────────────────────────────
    if min_sn:
        try:
            segments = client.read_time_segments(min_sn, DeviceFamily.MIN)
            _print_section(f"read_time_segments({min_sn!r})", segments)
            _ok(f"read_time_segments returned {len(segments)} segment(s)")
        except Exception as exc:
            _warn(f"read_time_segments failed (non-fatal): {exc}")

    print(f"\n{'═' * 60}")
    print("  Smoke test complete. All required calls succeeded.")
    print(f"{'═' * 60}\n")
    return 0


def _build_telemetry_calls(
    client: GrowattClient, sn: str, family: DeviceFamily
) -> list[tuple[str, object]]:
    """Return (label, callable) pairs for telemetry reads appropriate for *family*."""
    calls = [
        (f"device_detail({sn!r})", lambda: client.device_detail(sn, family)),
        (f"device_energy({sn!r})", lambda: client.device_energy(sn, family)),
    ]
    return calls


if __name__ == "__main__":
    sys.exit(main())
