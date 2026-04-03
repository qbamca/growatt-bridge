# Data Model: 001-api-redesign

Logical entities for the bridge API and persistence boundaries. Implementation uses Pydantic models in code; this document is the conceptual contract.

## Plant

| Field | Type | Notes |
|-------|------|--------|
| `plant_id` | string | Growatt plant identifier; from env `GROWATT_PLANT_ID` for MVP (single plant). |

**Relationships**: Has one or more **Devices** in Growatt Cloud; MVP configures one plant.

---

## Device

| Field | Type | Notes |
|-------|------|--------|
| `device_sn` | string | Serial number; from `GROWATT_DEVICE_SN`; must match `{device_sn}` path param (FR-020). |
| `family` | enum-like string | `MIN`, `SPH`, or `UNKNOWN` — drives normalization and supported ops. |

**Validation**: Unknown SN → **404**. UNKNOWN family → explicit unsupported response where required by spec edge cases.

**Relationships**: Belongs to a **Plant**; subject of parameters, telemetry, history, and writes.

---

## Operation (write allowlist)

| Field | Type | Notes |
|-------|------|--------|
| `operation_id` | string | Stable ID (e.g. allowlist key). |
| `parameter_schema` | map | Per-family constraints (FR-004, FR-006). |

**Rules**: Not on allowlist → **404** listing permitted ops (FR-006). Readonly mode → **403** on any write (FR-005).

---

## Command request

| Field | Type | Notes |
|-------|------|--------|
| `operation` | string | Must be allowlisted. |
| `parameters` | object | Key-value payload; validated before upstream (FR-004). |
| `device_sn` | string | From path; must match configured device list. |

---

## Command response

| Field | Type | Notes |
|-------|------|--------|
| `success` | boolean | Outcome of bridge + upstream execution. |
| `operation` | string | Echo operation id. |
| `device_sn` | string | Echo. |
| `detail` | optional string/object | Bridge-defined summary. |
| `readback` | optional object | Present when `BRIDGE_REQUIRE_READBACK=true`: contains `changed_fields`: `{ "field": { "before": …, "after": … } }` for changed fields only. |

---

## Audit entry (append-only JSONL)

Immutable record per write attempt (FR-009).

| Field | Type | Notes |
|-------|------|--------|
| `timestamp` | string (UTC ISO 8601) | When the attempt was processed. |
| `device_sn` | string | Target device. |
| `operation` | string | Operation id. |
| `parameters` | object | Redact secrets if ever introduced. |
| `result` | string or object | Success/failure summary; no raw upstream payload. |

---

## Device parameters (CAP-01)

Normalized map of configuration keys → values. Family-specific upstream names collapsed to **canonical** bridge field names (FR-003, FR-013).

### Read response scope (clarification)

The bridge **does not** echo the full upstream settings object (~270+ keys on MIN `readAllMinParam`). The **GET parameters** (CAP-01) response includes **only** the domains below so integrations see **operational settings** without grid-code, protection, reactive power, AFCI, identity, or seasonal/special schedule clutter.

| Domain | Purpose | Upstream keys included (MIN `readAllMinParam.msg` names) |
|--------|---------|-----------------------------------------------------------|
| **AC charging** | Grid → battery charging permission and limits | `acChargeEnable`, `ubAcChargingStopSOC`, `uwAcChargingMaxPowerLimit` |
| **Battery charge & power** | Charge/discharge power caps and SoC / auxiliary limits | `chargePowerCommand`, `disChargePowerCommand`, `onGridDischargeStopSOC`, `vbatWarning`, `vbatWarnClr`, `floatChargeCurrentLimit` |
| **General battery management** | Routine operating mode context (non-TOU, non–grid-export) | `bsystemWorkMode`, `onGridMode`, `bdcMode`, `haveBdc` |
| **TOU — normal schedule only** | Per-slot mode and forced windows (**primary**), optional encoded yearly rows | **Primary (use for normalized schedule):** `time1Mode`…`time9Mode`, `forcedTimeStart1`…`forcedTimeStart9`, `forcedTimeStop1`…`forcedTimeStop9`, `forcedStopSwitch1`…`forcedStopSwitch9`. **Secondary / diagnostic:** `yearTime1`…`yearTime9` — see [TOU schedule normalization](#tou-schedule-normalization). |
| **Grid export** | Export limiting and meter-backflow behaviour | `exportLimit`, `exportLimitPowerRate`, `backFlowSingleCtrl`, `backflowDefaultPower` |

**Explicitly out of scope for CAP-01 read** (still available to installers via Growatt; not returned by the bridge parameters endpoint): `season*`, `special*`, `yearMonthTime`, `yearSettingFlag`; winter-mode schedule fields (`winMode*`, `wchargeSOCLowLimit`, `wdisChargeSOCLowLimit`); voltage-based charge/discharge thresholds (`vbatStartforCharge`, `vbatStopForCharge`, `vbatStartForDischarge`, `vbatStopForDischarge`); grid protection / ride-through / Q(V) / PF / AFCI / firmware / plant metadata; demand management and peak shaving unless later promoted by a spec change.

### Downstream canonical names (CAP-01 JSON)

Downstream consumers see **short `snake_case` names** only — never raw Growatt camelCase. Names are **stable** for the MVP contract; additive fields may appear later with the same naming style.

**Conventions:** `snake_case`; booleans as JSON `true`/`false` where the value is boolean-like upstream (`0`/`1` normalized); percentages as numbers **0–100** unless noted; powers in **W** or **kW** as documented per field.

**Recommended response shape:** five top-level keys — `ac_charging`, `battery`, `battery_sys`, `grid_export`, and `tou` (object containing `slots` array). Flattening to one level is allowed for clients that need it; reuse the same leaf names.

| Canonical path | Upstream (MIN) | Meaning |
|----------------|----------------|---------|
| `ac_charging.on` | `acChargeEnable` | Grid may charge the battery (`0`/`1` → boolean) |
| `ac_charging.stop_soc` | `ubAcChargingStopSOC` | Stop AC charging at this SoC (%, number) |
| `ac_charging.max_kw` | `uwAcChargingMaxPowerLimit` | Max AC charging power (kW, number) |
| `battery.charge_power_pct` | `chargePowerCommand` | Max battery charge power (% of rated) |
| `battery.discharge_power_pct` | `disChargePowerCommand` | Max battery discharge power (% of rated) |
| `battery.discharge_stop_soc` | `onGridDischargeStopSOC` | On-grid: stop discharging below this SoC (%) |
| `battery.v_warn` | `vbatWarning` | Low battery warning voltage (V) |
| `battery.v_warn_clear` | `vbatWarnClr` | Warning clear voltage (V) |
| `battery.float_charge_a` | `floatChargeCurrentLimit` | Float charge current limit (A) |
| `battery_sys.mode` | `bsystemWorkMode` | Battery system work mode (enum) |
| `battery_sys.on_grid_mode` | `onGridMode` | On-grid mode variant (enum) |
| `battery_sys.bdc_mode` | `bdcMode` | BDC mode code |
| `battery_sys.bdc_present` | `haveBdc` | BDC module present (`0`/`1` → boolean) |
| `grid_export.on` | `exportLimit` | Export limiting enabled (`0`/`1` → boolean) |
| `grid_export.limit_pct` | `exportLimitPowerRate` | Export cap (% of rated or UI-defined unit) |
| `grid_export.per_phase` | `backFlowSingleCtrl` | Per-phase vs total export control (`0`/`1`) |
| `grid_export.fallback_w` | `backflowDefaultPower` | Fallback export cap if meter fails (W) |

**`tou` — array `tou.slots` (length 9):** each element:

| Field | Source | Meaning |
|-------|--------|---------|
| `i` | slot index `1…9` | Slot number (explicit, stable ordering) |
| `mode` | `time{N}Mode` | Slot mode (enum: load / battery / grid first, etc.) |
| `on` | `forcedStopSwitch{N}` | Slot enabled (`0`/`1` → boolean) |
| `start` | `forcedTimeStart{N}` | Start **`HH:MM`** (normalized, plant-local) |
| `end` | `forcedTimeStop{N}` | End **`HH:MM`** (normalized, plant-local) |

Example (illustrative):

```json
{
  "ac_charging": { "on": true, "stop_soc": 40, "max_kw": 12 },
  "battery": { "charge_power_pct": 100, "discharge_power_pct": 100, "discharge_stop_soc": 20 },
  "battery_sys": { "mode": 0, "on_grid_mode": 0, "bdc_mode": 255, "bdc_present": true },
  "grid_export": { "on": true, "limit_pct": 0, "per_phase": false, "fallback_w": 0 },
  "tou": {
    "slots": [
      { "i": 1, "mode": 1, "on": true, "start": "05:30", "end": "06:00" }
    ]
  }
}
```

(Production payload includes nine `slots` entries; one shown for brevity.)

**Flat alternative:** same leaf keys prefixed — e.g. `ac_charging_on`, `battery_charge_power_pct`, `tou_slots` (array) — only if a single-level schema is required; prefer nested objects above for clarity.

**Hard rule:** Responses **must not** include upstream Growatt key names (`camelCase` / `forcedTimeStart1`, etc.); mapping is bridge-internal only (FR-003).

### TOU schedule normalization

**Source of truth for user-facing slots:** Build the normalized TOU array from **`forcedTimeStart{N}`**, **`forcedTimeStop{N}`**, **`forcedStopSwitch{N}`**, and **`time{N}Mode`** only. The Shine portal and `growattServer` time-segment reads use this family of fields; they are easier to interpret than **`yearTime{N}`**.

**`yearTime{N}` vs `forced*`:** `yearTime` values are a **separate compact encoding** (several integers separated by `_`, e.g. mode / enable / start hour / minute / end hour / minute / flags). They **often will not match** the forced-window times after any manual conversion, and **timezone adjustment does not explain the gap** — the two representations are not guaranteed to be the same schedule layer (e.g. yearly template vs active forced windows, or firmware-internal vs UI path). The bridge **must not** infer one from the other or merge them without a documented rule. For CAP-01, **expose times derived from `forced*` + `time*Mode`**; include `yearTime*` only if explicitly needed for diagnostics (otherwise omit to avoid contradiction).

**Time string normalization (mandatory):** Upstream strings use **`H:M`** with **unpadded** hours and minutes (`10:1`, `14:0`, `0:0`). The bridge **must** normalize every start/stop to **`HH:MM`** in **24-hour local plant time** (same convention as Growatt UI for that plant):

| Raw | Normalized |
|-----|------------|
| `10:1` | `10:01` |
| `14:0` | `14:00` |
| `6:0` | `06:00` |
| `0:0` | `00:00` |

**Algorithm (normative):** Parse `^(\d{1,2}):(\d{1,2})$`, interpret as hour and minute, validate `0–23` and `0–59`, emit `f"{hour:02d}:{minute:02d}"`. Invalid tokens → surface a validation/502 path per FR-008 (do not pass through opaque strings to clients for normalized fields).

**Inactive slots:** `forcedStopSwitch{N} == 0` or mode `0` may pair with `0:0` start/stop; still normalize times to `00:00` where present so clients always see a consistent pattern; semantics of “disabled” come from **switch + mode**, not from omitting times.

### MIN upstream exploration (full key list — not API output)

**2026-04-03** — Full settings snapshot from Shine `POST …/tcpSet.do` `action=readAllMinParam` is used **only for engineering / mapping** (see `scripts/explore/fetch_min_params.py`). Field names are abbreviated internal identifiers; “decryption” in exploration scripts means **label mapping**, not crypto.

| Metric | Value |
|--------|------:|
| Keys in sample capture (`msg`) | 273 |
| Keys with labels in `scripts/explore/min_param_key_label.py` | 273 |
| Heuristic `misc` labels | 3 (`eMonth`, `compatibleFlag`, `sysMtncAvail`) |

**Primary doc reference**: `docs/parameter-glossary.md` §4 — same logical fields as `readAllMinParam.msg`.

**Regenerate full exploratory table** (not the CAP-01 contract):

```bash
python scripts/explore/map_read_all_min_param.py
```

---

## Telemetry snapshot (CAP-03)

Point-in-time normalized fields: PV, grid, battery (SOC etc. when present), load, etc. Battery fields **omitted** when device has no battery (FR-014). Exact schema **TBD per empirical contract** (FR-016).

---

## Historical record (CAP-04)

Time-bucketed energy rows (daily / monthly minimum). Empty list when no data (FR-015). Bucket labeling vs UTC **TBD per empirical contract** (FR-016, FR-025).

---

## Error envelope (API)

Cross-cutting type for **4xx/5xx/429** responses (FR-008). Includes machine-readable `code`, human message, optional `details`, and for rate limit **`retry_after_seconds`** aligned with `Retry-After` header. See `contracts/error-envelope.schema.json`.

---

## State transitions (session)

Not entity CRUD — **Shine session**: unauthenticated → authenticated (cookies + JWT scheduling) → proactive refresh before `exp` → on failure, reactive re-auth once → terminal error to caller if retry fails (FR-017).
