#!/usr/bin/env python3
"""
Test OpenAPI V1 Growatt API.
Initialize with token, fetch plants/devices, and device-specific data. Log results (secrets redacted).

Device types: 5=SPH (MIX hybrid), 7=MIN (TLX). Use sph_* for type 5, min_* for type 7.
Batteries: type 2 = storage (separate device). For MIN/SPH, battery data may be in inverter response.
"""

import json
import os
import sys
from pathlib import Path

# Add src to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "src"))

from dotenv import load_dotenv

load_dotenv(SCRIPT_DIR.parent / ".env")

from growatt_explorer.client import get_openapi_v1_client, redact

# Import for error details (optional - growattServer may not be installed in all envs)
try:
    from growattServer.exceptions import GrowattV1ApiError
except ImportError:
    GrowattV1ApiError = None


def log(label: str, data, redact_secrets: bool = True) -> None:
    """Print labeled JSON, optionally redacted."""
    payload = redact(data) if redact_secrets else data
    print(f"\n--- {label} ---")
    print(json.dumps(payload, indent=2, default=str))
    print()


def main() -> int:
    """Run OpenAPI V1 tests."""
    try:
        api = get_openapi_v1_client()
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    print("Testing OpenAPI V1...")

    try:
        plant_data = api.plant_list()
        log("plant_list", plant_data)
        plants = plant_data.get("plants", plant_data) if isinstance(plant_data, dict) else plant_data
        if isinstance(plants, dict):
            plants = plants.get("plants", [])
        if not plants:
            print("No plants found. Exiting.")
            return 0
    except Exception as e:
        print(f"ERROR: plant_list failed: {e}")
        return 1

    # plant_list returns dict with 'plants' key, each plant has 'id' or 'plantId'
    plant_id = None
    for p in plants:
        plant_id = p.get("id") or p.get("plantId") or p.get("plant_id")
        if plant_id:
            break
    if not plant_id:
        print("ERROR: Could not extract plant_id from plant_list")
        return 1

    try:
        plant_details = api.plant_details(plant_id)
        log("plant_details", plant_details)
    except Exception as e:
        print(f"ERROR: plant_details failed: {e}")
        return 1

    try:
        devices_data = api.device_list(plant_id)
        log("device_list", devices_data)
    except Exception as e:
        print(f"ERROR: device_list failed: {e}")
        return 1

    # device_list: type 5=SPH (MIX hybrid), 7=MIN (TLX), 2=storage (battery), 3=other (meter)
    devices = (
        devices_data.get("devices", [])
        if isinstance(devices_data, dict)
        else (devices_data if isinstance(devices_data, list) else [])
    )
    sph_sn = None
    min_sn = None
    has_battery = False
    for dev in devices:
        dev_type = dev.get("deviceType") or dev.get("type") or dev.get("device_type")
        dev_type = int(dev_type) if dev_type not in (None, "") else None
        sn = dev.get("device_sn") or dev.get("serialNum") or dev.get("deviceSn") or dev.get("sn")
        if dev_type == 5 and sn and sn != "meter":
            sph_sn = sn
        elif dev_type == 7 and sn and sn != "meter":
            min_sn = sn
        elif dev_type == 2:
            has_battery = True
    if not sph_sn and not min_sn and devices:
        first = next((d for d in devices if (d.get("device_sn") or "").lower() != "meter"), None)
        if first:
            sn = first.get("device_sn") or first.get("serialNum") or first.get("deviceSn")
            t = first.get("type") or first.get("device_type")
            if sn:
                if t == 5:
                    sph_sn = sn
                elif t == 7:
                    min_sn = sn
                else:
                    min_sn = sn  # fallback: try as MIN (common for TLX)

    def err_detail(e):
        if GrowattV1ApiError and isinstance(e, GrowattV1ApiError):
            return f" (error_code={getattr(e, 'error_code', '?')}, error_msg={getattr(e, 'error_msg', '')!r})"
        return ""

    # SPH (type 5) - MIX hybrid inverters
    if sph_sn:
        for name, fn in [
            ("sph_detail", lambda: api.sph_detail(sph_sn)),
            ("sph_energy", lambda: api.sph_energy(sph_sn)),
            ("sph_energy_history", lambda: api.sph_energy_history(sph_sn)),
        ]:
            try:
                log(name, fn())
            except Exception as e:
                print(f"WARN: {name} failed: {e}{err_detail(e)}")
    else:
        print("No SPH (type 5) device found. Skipping sph_* calls.")

    # MIN (type 7) - TLX inverters (includes battery-capable models like SPF)
    if min_sn:
        for name, fn in [
            ("min_detail", lambda: api.min_detail(min_sn)),
            ("min_energy", lambda: api.min_energy(min_sn)),
            ("min_energy_history", lambda: api.min_energy_history(min_sn)),
        ]:
            try:
                log(name, fn())
            except Exception as e:
                print(f"WARN: {name} failed: {e}{err_detail(e)}")
    else:
        print("No MIN (type 7) device found. Skipping min_* calls.")

    if not has_battery:
        print(
            "\nNote: No type-2 (storage/battery) device in device_list. "
            "For MIN/SPH hybrids, battery data may be embedded in inverter min_detail/sph_detail."
        )

    print("\nOpenAPI V1 test completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
