#!/usr/bin/env python3
"""Live probe: read → tlxSet test value → verify → restore for MIN write parameters.

Confirms Shine ``POST …/tcpSet.do`` ``action=tlxSet`` types used in ``data-model.md``:
``ac_charge``, ``ub_ac_charging_stop_soc``, ``time_segment1``. For each parameter,
captures the previous value, applies a **small reversible** change, re-reads
``readAllMinParam``, restores the original value, and re-reads again.

**Requires** real credentials (same as other explore scripts). Writes briefly touch
the inverter settings — run only when acceptable for your plant.

Environment (repo ``.env``):

    GROWATT_WEB_USERNAME   GROWATT_WEB_PASSWORD
    GROWATT_PLANT_ID       GROWATT_DEVICE_SN
    GROWATT_WEB_BASE_URL   optional

Usage::

    python scripts/explore/probe_tlx_write_roundtrip.py
    python scripts/explore/probe_tlx_write_roundtrip.py --dry-run
    python scripts/explore/probe_tlx_write_roundtrip.py --skip-ac-charge --skip-time-segment

Artifacts under ``audit/explore/``:

    * ``<ts>_tlx_write_roundtrip.json`` — full structured report (steps + responses)
    * Individual ``<ts>_tlx_write_step_*.json`` files per write (optional detail)

Stdout logs each **parameter → from → test → restored** line for quick grep.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
sys.path.insert(0, str(_SRC))

from growatt_bridge.legacy_shine_web import (  # noqa: E402
    LegacyShineWebClient,
    LegacyShineWebError,
)

from _base import fail, info, ok, require_env, save_json_artifact  # noqa: E402

_REDACT = {"password", "token"}


def _msg(client: LegacyShineWebClient, plant_id: str, serial: str) -> dict[str, Any]:
    raw = client.read_all_min_param(plant_id, serial)
    if not isinstance(raw, dict):
        return {}
    m = raw.get("msg")
    return m if isinstance(m, dict) else {}


def _parse_hh_mm(s: str) -> tuple[int, int]:
    s = (s or "").strip().strip('"')
    if ":" not in s:
        return 0, 0
    a, b = s.split(":", 1)
    return int(a), int(b)


def _add_one_minute(h: int, m: int) -> tuple[int, int]:
    m2 = m + 1
    if m2 >= 60:
        return (h + 1) % 24, 0
    return h, m2


def _fmt_hh_mm(h: int, m: int) -> str:
    return f"{h}:{m}"


@dataclass
class StepResult:
    parameter: str
    before: Any
    test_applied: Any
    after_test_read: Any | None = None
    restored_value: Any = None
    after_restore_read: Any | None = None
    write_responses: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: "***" if k in _REDACT else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _append_step_report(tag: str, body: dict[str, Any]) -> None:
    path = save_json_artifact(
        f"tlx_write_step_{tag}",
        {"response_body": _redact(body)},
    )
    info(f"saved step artifact → {path}")


def probe_ac_charge(
    client: LegacyShineWebClient,
    plant_id: str,
    serial: str,
    msg: dict[str, Any],
    *,
    save_steps: bool,
    steps_out: list[StepResult],
) -> None:
    sr = StepResult(parameter="ac_charge", before=None, test_applied=None)
    before = str(msg.get("acChargeEnable", "0"))
    sr.before = before
    test = "0" if before == "1" else "1"
    sr.test_applied = test
    try:
        out = client.tcp_set_scalar(plant_id, serial, "ac_charge", test)
        sr.write_responses.append({"phase": "test", "body": out})
        if save_steps:
            _append_step_report("ac_charge_test", out)
        msg2 = _msg(client, plant_id, serial)
        sr.after_test_read = str(msg2.get("acChargeEnable", ""))

        out_r = client.tcp_set_scalar(plant_id, serial, "ac_charge", before)
        sr.write_responses.append({"phase": "restore", "body": out_r})
        if save_steps:
            _append_step_report("ac_charge_restore", out_r)
        msg3 = _msg(client, plant_id, serial)
        sr.restored_value = before
        sr.after_restore_read = str(msg3.get("acChargeEnable", ""))
    except Exception as exc:  # noqa: BLE001 — exploratory script
        sr.errors.append(str(exc))
    steps_out.append(sr)


def probe_ub_ac_charging_stop_soc(
    client: LegacyShineWebClient,
    plant_id: str,
    serial: str,
    msg: dict[str, Any],
    *,
    save_steps: bool,
    steps_out: list[StepResult],
) -> None:
    sr = StepResult(parameter="ub_ac_charging_stop_soc", before=None, test_applied=None)
    raw = msg.get("ubAcChargingStopSOC", "50")
    try:
        before = int(str(raw))
    except ValueError:
        before = 50
    sr.before = before
    if before >= 100:
        test = before - 1
    elif before <= 0:
        test = 1
    else:
        test = before + 1
    sr.test_applied = test
    try:
        out = client.tcp_set_scalar(plant_id, serial, "ub_ac_charging_stop_soc", str(test))
        sr.write_responses.append({"phase": "test", "body": out})
        if save_steps:
            _append_step_report("ub_soc_test", out)
        msg2 = _msg(client, plant_id, serial)
        sr.after_test_read = str(msg2.get("ubAcChargingStopSOC", ""))

        out_r = client.tcp_set_scalar(plant_id, serial, "ub_ac_charging_stop_soc", str(before))
        sr.write_responses.append({"phase": "restore", "body": out_r})
        if save_steps:
            _append_step_report("ub_soc_restore", out_r)
        msg3 = _msg(client, plant_id, serial)
        sr.restored_value = before
        sr.after_restore_read = str(msg3.get("ubAcChargingStopSOC", ""))
    except Exception as exc:  # noqa: BLE001
        sr.errors.append(str(exc))
    steps_out.append(sr)


def probe_time_segment1(
    client: LegacyShineWebClient,
    plant_id: str,
    serial: str,
    msg: dict[str, Any],
    *,
    save_steps: bool,
    steps_out: list[StepResult],
) -> None:
    sr = StepResult(parameter="time_segment1", before=None, test_applied=None)
    try:
        mode = int(str(msg.get("time1Mode", "0")))
    except ValueError:
        mode = 0
    sh, sm = _parse_hh_mm(str(msg.get("forcedTimeStart1", "0:0")))
    eh, em = _parse_hh_mm(str(msg.get("forcedTimeStop1", "0:0")))
    en = str(msg.get("forcedStopSwitch1", "0")) == "1"
    before = {
        "time1Mode": mode,
        "forcedTimeStart1": _fmt_hh_mm(sh, sm),
        "forcedTimeStop1": _fmt_hh_mm(eh, em),
        "forcedStopSwitch1": en,
    }
    sr.before = before
    tsh, tsm = _add_one_minute(sh, sm)
    test = {**before, "forcedTimeStart1": _fmt_hh_mm(tsh, tsm)}
    sr.test_applied = test
    try:
        out = client.tcp_set_time_segment(
            plant_id,
            serial,
            1,
            mode,
            tsh,
            tsm,
            eh,
            em,
            en,
        )
        sr.write_responses.append({"phase": "test", "body": out})
        if save_steps:
            _append_step_report("time_seg1_test", out)
        msg2 = _msg(client, plant_id, serial)
        sr.after_test_read = {
            "forcedTimeStart1": msg2.get("forcedTimeStart1"),
            "forcedTimeStop1": msg2.get("forcedTimeStop1"),
            "time1Mode": msg2.get("time1Mode"),
            "forcedStopSwitch1": msg2.get("forcedStopSwitch1"),
        }

        out_r = client.tcp_set_time_segment(
            plant_id,
            serial,
            1,
            mode,
            sh,
            sm,
            eh,
            em,
            en,
        )
        sr.write_responses.append({"phase": "restore", "body": out_r})
        if save_steps:
            _append_step_report("time_seg1_restore", out_r)
        msg3 = _msg(client, plant_id, serial)
        sr.restored_value = before
        sr.after_restore_read = {
            "forcedTimeStart1": msg3.get("forcedTimeStart1"),
            "forcedTimeStop1": msg3.get("forcedTimeStop1"),
            "time1Mode": msg3.get("time1Mode"),
            "forcedStopSwitch1": msg3.get("forcedStopSwitch1"),
        }
    except Exception as exc:  # noqa: BLE001
        sr.errors.append(str(exc))
    steps_out.append(sr)


def main() -> int:
    parser = argparse.ArgumentParser(description="tlxSet round-trip live probe (MIN inverter).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="only read readAllMinParam and print what would change (no writes)",
    )
    parser.add_argument("--skip-ac-charge", action="store_true")
    parser.add_argument("--skip-ub-soc", action="store_true")
    parser.add_argument("--skip-time-segment", action="store_true")
    parser.add_argument(
        "--save-step-files",
        action="store_true",
        help="also write per-step JSON files (in addition to the combined report)",
    )
    args = parser.parse_args()

    env = require_env(
        "GROWATT_WEB_USERNAME",
        "GROWATT_WEB_PASSWORD",
        "GROWATT_PLANT_ID",
        "GROWATT_DEVICE_SN",
    )
    base_url = os.environ.get("GROWATT_WEB_BASE_URL", "https://server.growatt.com/")
    plant_id = env["GROWATT_PLANT_ID"]
    serial = env["GROWATT_DEVICE_SN"]

    print("\nProbe : tlx_write_roundtrip (live tcpSet.do tlxSet)")
    print(f"Base  : {base_url}")
    print(f"Plant : {plant_id}")
    print(f"SN    : {serial}")
    if args.dry_run:
        info("DRY RUN — no tlxSet calls will be made")

    client = LegacyShineWebClient(
        base_url,
        env["GROWATT_WEB_USERNAME"],
        env["GROWATT_WEB_PASSWORD"],
    )
    try:
        client.login()
    except LegacyShineWebError as exc:
        fail(str(exc))
        return 1

    msg0 = _msg(client, plant_id, serial)
    if not msg0:
        fail("readAllMinParam returned empty msg — check SN/plant/credentials")
        return 1

    baseline_snapshot = {
        "acChargeEnable": msg0.get("acChargeEnable"),
        "ubAcChargingStopSOC": msg0.get("ubAcChargingStopSOC"),
        "time1Mode": msg0.get("time1Mode"),
        "forcedTimeStart1": msg0.get("forcedTimeStart1"),
        "forcedTimeStop1": msg0.get("forcedTimeStop1"),
        "forcedStopSwitch1": msg0.get("forcedStopSwitch1"),
    }
    print("\n── Baseline (readAllMinParam.msg excerpt) ──")
    print(json.dumps(baseline_snapshot, indent=2))

    steps: list[StepResult] = []

    if args.dry_run:
        # describe intended mutations only
        ac = str(msg0.get("acChargeEnable", "0"))
        flip = "0" if ac == "1" else "1"
        info(f"[dry-run] ac_charge: would toggle acChargeEnable {ac} → {flip} → restore {ac}")
        try:
            bs = int(str(msg0.get("ubAcChargingStopSOC", "50")))
        except ValueError:
            bs = 50
        tst = bs + 1 if bs < 100 else bs - 1
        info(f"[dry-run] ub_ac_charging_stop_soc: would set {bs} → {tst} → restore {bs}")
        sh, sm = _parse_hh_mm(str(msg0.get("forcedTimeStart1", "0:0")))
        tsh, tsm = _add_one_minute(sh, sm)
        info(
            "[dry-run] time_segment1: would nudge forcedTimeStart1 "
            f"{_fmt_hh_mm(sh, sm)} → {_fmt_hh_mm(tsh, tsm)} then restore"
        )
        report = {
            "dry_run": True,
            "baseline": baseline_snapshot,
        }
        out = save_json_artifact("tlx_write_roundtrip", report)
        ok(f"Saved report → {out}")
        return 0

    if not args.skip_ac_charge:
        probe_ac_charge(
            client,
            plant_id,
            serial,
            msg0,
            save_steps=args.save_step_files,
            steps_out=steps,
        )
    if not args.skip_ub_soc:
        probe_ub_ac_charging_stop_soc(
            client,
            plant_id,
            serial,
            msg0,
            save_steps=args.save_step_files,
            steps_out=steps,
        )
    if not args.skip_time_segment:
        probe_time_segment1(
            client,
            plant_id,
            serial,
            msg0,
            save_steps=args.save_step_files,
            steps_out=steps,
        )

    print("\n── Change log (parameter: before → test → after read | restore → after read) ──")
    for s in steps:
        if s.skipped:
            print(f"  {s.parameter}: SKIPPED ({s.skip_reason})")
            continue
        line = (
            f"  {s.parameter}: before={s.before!r} → test={s.test_applied!r} "
            f"→ read_after_test={s.after_test_read!r} | restored={s.restored_value!r} "
            f"→ read_after_restore={s.after_restore_read!r}"
        )
        print(line)
        if s.errors:
            for e in s.errors:
                fail(f"{s.parameter}: {e}")

    report = {
        "baseline": baseline_snapshot,
        "steps": [
            {
                "parameter": s.parameter,
                "before": s.before,
                "test_applied": s.test_applied,
                "after_test_read": s.after_test_read,
                "restored_value": s.restored_value,
                "after_restore_read": s.after_restore_read,
                "write_responses": _redact(s.write_responses),
                "errors": s.errors,
                "skipped": s.skipped,
                "skip_reason": s.skip_reason,
            }
            for s in steps
        ],
    }
    out = save_json_artifact("tlx_write_roundtrip", report)
    ok(f"Full report → {out}")

    failed = any(s.errors for s in steps)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
