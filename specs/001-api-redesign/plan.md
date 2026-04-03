# Implementation Plan: Growatt Bridge API Redesign

**Branch**: `001-api-redesign` | **Date**: 2026-04-03 | **Spec**: `/home/qbamca/mechanical-joe/growatt-bridge/specs/001-api-redesign/spec.md`

**Note**: This iteration adds **TLX live telemetry** to `data-model.md` (empirical JSON from `newTlxApi.do` and documented behaviour of Shine panel `/panel/tlx/*_bdc` XHR). Earlier work covered **CAP-02 inverter write parameters**: Shine `tcpSet.do` `tlxSet`, permission ordering, and the writable-parameter catalog. `research.md` §11 documents the write-path decision.

## Summary

The bridge exposes a **bounded** write surface: only explicitly modeled **`operation_id`** values may be sent upstream as Shine **`type=`** on **`POST …/tcpSet.do`** with **`action=tlxSet`**. On every write, the service applies **`BRIDGE_READONLY`** → **`BRIDGE_WRITE_ALLOWLIST`** (comma-separated `operation_id` list) → **validation** → upstream. The initial catalog covers **`ac_charge`**, **`ub_ac_charging_stop_soc`**, and **`time_segment1`…`time_segment9`** (nine TOU slots, one upstream `type` per slot). Full logical detail: `/home/qbamca/mechanical-joe/growatt-bridge/specs/001-api-redesign/data-model.md` (sections **Operation** and **Inverter write parameters (CAP-02)**).

### Telemetry (empirical, 2026-04-03)

- **Probe:** `scripts/explore/fetch_tlx_telemetry.py` saves artifacts under `audit/explore/` (gitignored).
- **Stable upstream for programmatic session:** `POST newTlxApi.do` with `op=getSystemStatus_KW` (instantaneous TLX status) and `op=getEnergyOverview` (today / total energy counters). Same `newTwoLoginAPI` + plant/device cookie context as `readAllMinParam` / `tlxSet`.
- **Shine UI parity:** In-browser `fetch()` targets `…/panel/tlx/getTLXStatusData_bdc` and `getTLXTotalData_bdc` (`tlxSn`, `plantId` query). Those routes returned **302 → not logged in** when using only API login cookies in the probe; capturing their JSON requires pasting **`GROWATT_BROWSER_COOKIE`** (full Cookie header from a logged-in browser tab). See **TLX live telemetry** in `data-model.md` for field tables and mapping notes.
- **Downstream contract (TLX):** The bridge passes through **only** these upstream `obj` keys — **instantaneous:** `SOC`, `chargePower`, `pdisCharge`, `ppv`, `pactouser`, `pactogrid`, `pLocalLoad`; **energy today:** `epvToday`, `elocalLoadToday`, `echargetoday`, `edischargeToday`, `etoGridToday`. Full detail and exclusions: `data-model.md` section **Downstream TLX telemetry (keys passed to clients)**.
- **Freshness:** Status data is meaningful at **~5 minute** resolution; responses should remain cached or rate-limited accordingly (no implementation change required in this doc beyond alignment with the bridge cache policy).

## Technical Context

**Language/Version**: Python ≥3.11 (`pyproject.toml`)  
**Primary Dependencies**: FastAPI ≥0.115, Uvicorn, Pydantic v2, pydantic-settings, requests, growattServer  
**Storage**: N/A for bridge state beyond optional append-only audit JSONL (`BRIDGE_AUDIT_LOG`)  
**Testing**: pytest, httpx (dev); integration tests against real Growatt per spec (FR-012)  
**Target Platform**: Linux / container (Docker Compose with consumer)  
**Project Type**: web-service (HTTP facade)  
**Performance Goals**: Bounded by single global upstream FIFO (FR-022) and sliding 60s upstream rate limit (FR-010)  
**Constraints**: Plain HTTP MVP; no raw upstream errors to clients (FR-008); strict write allowlist (FR-006)  
**Scale/Scope**: Single plant / single device MVP; header-based API versioning (FR-021)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still a **placeholder template** (no project-specific gates). No enforceable constitution violations identified for this design iteration. Revisit when the constitution is ratified.

## Project Structure

### Documentation (this feature)

```text
specs/001-api-redesign/
├── plan.md              # This file
├── research.md          # Phase 0 / decisions
├── data-model.md        # Entities + CAP-01/CAP-02 logical model
├── quickstart.md
├── contracts/
└── tasks.md             # Phase 2 (/speckit.tasks) — not created here
```

### Source Code (repository root)

```text
src/
└── growatt_bridge/
    └── ...

tests/
└── ...
```

**Structure Decision**: Single Python package under `src/growatt_bridge/` with tests under `tests/` (setuptools `where = ["src"]`).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No additional complexity entries for this iteration.
