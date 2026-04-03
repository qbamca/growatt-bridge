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
| `operation_id` | string | Stable bridge ID for one writable **parameter family**. For MVP it **may equal** the Shine `type=` string (e.g. `ac_charge`, `ub_ac_charging_stop_soc`, `time_segment1`…`time_segment9`) to keep mapping obvious; if names diverge later, maintain a fixed internal map from `operation_id` → upstream `type`. |
| `upstream_type` | string | Value sent as `type=` on `tlxSet` (see [Inverter write parameters (CAP-02)](#inverter-write-parameters-cap-02)). |
| `parameter_schema` | map | Constraints for `param1`…`paramN` / JSON payload fields (FR-004); may vary by **Device.family** when empirically required. |

**Permission checks (normative, every write):**

1. **`BRIDGE_READONLY=true`** → **403** for any mutating write path (FR-005); no upstream call.
2. **Configurable allowlist** — env **`BRIDGE_WRITE_ALLOWLIST`** is a comma-separated list of permitted **`operation_id`** values. If the requested operation is **not** in that set → **404** with a response that lists permitted operations (FR-006). Empty allowlist means **no** writes are permitted even when `BRIDGE_READONLY=false`.
3. **Validation** — payload must match the schema for that operation (ranges, arity, types) → **422** with field-level errors if not (FR-004); rejection happens **before** any upstream `tcpSet.do` call.

**Evolution**: New writable parameters are added by extending the **catalog** below, defining validation + upstream mapping, and **including the new `operation_id` in deployment config** (`BRIDGE_WRITE_ALLOWLIST`). No runtime discovery of arbitrary upstream `type=` strings — only explicitly modeled operations are valid.

---

## Inverter write parameters (CAP-02)

Writes go to the Shine portal **`POST …/tcpSet.do`** with form body (application/x-www-form-urlencoded), **not** the OpenAPI token API. The bridge forwards only operations that pass the [permission checks](#operation-write-allowlist) above.

### Upstream request shape (`tlxSet`)

| Form field | Example / notes |
|------------|-------------------|
| `action` | `tlxSet` |
| `serialNum` | Target inverter serial — bridge fills from configured / validated `{device_sn}` (must match `GROWATT_DEVICE_SN` / `GET /devices` for MVP). |
| `type` | Upstream parameter key — examples: `ac_charge`, `ub_ac_charging_stop_soc`, `time_segment1`…`time_segment9` (see catalog). |
| `param1` … `param6` | Integer or string slots as required by `type` (see catalog). Omitted slots are not sent. |

**Illustrative raw bodies** (from live probes; serial is illustrative):

```
action=tlxSet&serialNum=TSS1F5M04Y&type=ac_charge&param1=0
action=tlxSet&serialNum=TSS1F5M04Y&type=ub_ac_charging_stop_soc&param1=42
action=tlxSet&serialNum=TSS1F5M04Y&type=time_segment1&param1=1&param2=05&param3=30&param4=06&param5=00&param6=1
```

(`time_segment2`…`time_segment9` use the same `param1`…`param6` layout; the **slot index N** is selected only by **`type=time_segmentN`** — see [TOU `time_segmentN` encoding](#tou-time_segmentn-encoding).)

### Writable parameter catalog (initial subset)

Only the operations below are in scope for the bridge **until** the spec adds more rows. Each row is one **allowlist entry** (`operation_id`). The service is **not** entitled to send any other `type=` via `tlxSet`.

| `operation_id` | Upstream `type=` | Params | Meaning (informal) | CAP-01 read cross-ref |
|----------------|------------------|--------|---------------------|------------------------|
| `ac_charge` | `ac_charge` | `param1`: `0` / `1` | AC (grid) charging enable/disable. | `ac_charging.on` |
| `ub_ac_charging_stop_soc` | `ub_ac_charging_stop_soc` | `param1`: integer | Stop AC charging at this battery SoC (%). | `ac_charging.stop_soc` |
| `time_segment1` | `time_segment1` | `param1`…`param6` | TOU time segment **1** (see [TOU `time_segmentN` encoding](#tou-time_segmentn-encoding)). | `tou.slots[0]` (`i === 1`) |
| `time_segment2` | `time_segment2` | `param1`…`param6` | TOU time segment **2**. | `tou.slots[1]` (`i === 2`) |
| `time_segment3` | `time_segment3` | `param1`…`param6` | TOU time segment **3**. | `tou.slots[2]` (`i === 3`) |
| `time_segment4` | `time_segment4` | `param1`…`param6` | TOU time segment **4**. | `tou.slots[3]` (`i === 4`) |
| `time_segment5` | `time_segment5` | `param1`…`param6` | TOU time segment **5**. | `tou.slots[4]` (`i === 5`) |
| `time_segment6` | `time_segment6` | `param1`…`param6` | TOU time segment **6**. | `tou.slots[5]` (`i === 6`) |
| `time_segment7` | `time_segment7` | `param1`…`param6` | TOU time segment **7**. | `tou.slots[6]` (`i === 7`) |
| `time_segment8` | `time_segment8` | `param1`…`param6` | TOU time segment **8**. | `tou.slots[7]` (`i === 8`) |
| `time_segment9` | `time_segment9` | `param1`…`param6` | TOU time segment **9**. | `tou.slots[8]` (`i === 9`) |

**Allowlisting TOU writes**: Operators add **`time_segment1`** through **`time_segment9`** (or any subset) to **`BRIDGE_WRITE_ALLOWLIST`**. Granting segment **N** implies that **`operation_id`** `time_segment{N}` is permitted — there is no separate “bulk TOU” operation; changing multiple slots requires one upstream `tlxSet` per slot (each subject to FR-022 serialization and FR-010 rate limits).

#### TOU `time_segmentN` encoding

Example for **`type=time_segment1`** (`param1=1&param2=05&param3=30&param4=06&param5=00&param6=1`): segment **1**, **battery-first** priority (`param1=1`), **05:30–06:00**, segment **enabled** (`param6=1`). The same **`param1`…`param6` semantics** apply for **`time_segment2`…`time_segment9`**; only the **`type`** name changes to select the slot (**N**).

| Param | Interpretation |
|-------|----------------|
| `param1` | **Energy priority / dispatch mode** for this segment (maps to read-side `time{N}Mode` and bridge JSON **`mode`**): **`0`** = **load-first** — prioritize supplying household loads from available PV / battery before other goals; **`1`** = **battery-first** — prioritize charging or managing the battery within this window; **`2`** = **grid-first** — prioritize grid import/export behavior for this segment (e.g. timed grid charging when AC charge is enabled — see device docs). |
| `param2`, `param3` | Start time — hour and minute (example: `05`, `30` → `05:30`). |
| `param4`, `param5` | End time — hour and minute (example: `06`, `00` → `06:00`). |
| `param6` | Segment **enabled** (`0` = disabled, `1` = enabled). |

**Validation**: Safe ranges (SoC bounds, valid clock fields, allowed `param1` for `ac_charge`, **`param1 ∈ {0,1,2}`** for `time_segmentN`, slot **`N ∈ [1,9]`** implied by **`type`**) are **per operation** and must be enforced before upstream submission (FR-004). Exact numeric bounds **TBD** from empirical tests (FR-016) where not already fixed by hardware docs.

### Write endpoint (client HTTP)

This is what **callers send to the bridge** (not the upstream Growatt form). Same JSON body is used for the **mutating** write and for the **dry-run validate** route (FR-007); only the path differs.

| | |
|--|--|
| **Method / path (execute write)** | `POST /devices/{device_sn}/write` |
| **Method / path (validate only)** | `POST /devices/{device_sn}/write/validate` |
| **Path parameter** | `{device_sn}` — inverter serial; MUST match a device from `GET /devices` (FR-020). |

**Headers (FR-021)**

| Header | Value |
|--------|--------|
| `Accept` | MUST include a supported version, e.g. `application/vnd.growatt-bridge.v1+json` (see `contracts/versioning.md`). |
| `Content-Type` | Same vendor JSON media type as the request body, e.g. `application/vnd.growatt-bridge.v1+json`. |

**JSON body (required)** — object with exactly two top-level keys:

| Field | Type | Description |
|-------|------|-------------|
| `operation` | string | **`operation_id`** from the [writable catalog](#writable-parameter-catalog-initial-subset) (e.g. `ac_charge`, `ub_ac_charging_stop_soc`, `time_segment3`). |
| `parameters` | object | **Operation-specific** payload — only the keys listed for that `operation` below; unknown keys MUST be rejected (422). |

Machine-readable schema: `contracts/write-request.schema.json`.

**Normative `parameters` by `operation`**

| `operation` | `parameters` keys | Types / rules |
|---------------|-------------------|----------------|
| `ac_charge` | `enabled` | boolean — `true` = AC charging on, `false` = off (maps to upstream `param1` `1`/`0`). |
| `ub_ac_charging_stop_soc` | `stop_soc` | integer — stop AC charging at this state-of-charge (%); bridge enforces safe range per FR-004 / empirical bounds. |
| `time_segment1` … `time_segment9` | `mode`, `start`, `end`, `active` | **`mode`**: integer **`0`**, **`1`**, or **`2`** — load-first / battery-first / grid-first (maps to upstream **`param1`**; see [TOU encoding](#tou-time_segmentn-encoding)). `start` / `end`: strings **`HH:MM`** (24-hour, normalized, e.g. `"05:30"`). **`active`**: boolean (maps to **`param6`**). The segment index **N** is taken **only** from `operation` (`time_segment7` → slot 7); clients MUST NOT send a separate slot field. |

**Examples**

```http
POST /devices/TSS1F5M04Y/write HTTP/1.1
Host: localhost:8081
Accept: application/vnd.growatt-bridge.v1+json
Content-Type: application/vnd.growatt-bridge.v1+json
```

```json
{
  "operation": "ub_ac_charging_stop_soc",
  "parameters": { "stop_soc": 42 }
}
```

```json
{
  "operation": "time_segment1",
  "parameters": {
    "mode": 1,
    "start": "05:30",
    "end": "06:00",
    "active": true
  }
}
```

```json
{
  "operation": "ac_charge",
  "parameters": { "enabled": false }
}
```

### Mapping client JSON to upstream `tlxSet`

The bridge maps **`operation`** + **`parameters`** to Shine `POST …/tcpSet.do` (`action=tlxSet`, `type=…`, `param1`…). For TOU, the slot index **N** is **derived from `operation`** (`time_segmentN` → **`type=time_segmentN`** only — not sent as `param1`).

| `operation` | `parameters` → upstream |
|-------------|-------------------------|
| `ac_charge` | `enabled` → `param1` = `1` or `0` |
| `ub_ac_charging_stop_soc` | `stop_soc` → `param1` |
| `time_segmentN` | `mode` → **`param1`** (`0`/`1`/`2`); `start`/`end` → hour/minute → `param2`…`param5`; `active` → `param6` | [TOU encoding](#tou-time_segmentn-encoding) |

Times MUST use **`HH:MM`** in JSON; invalid values → **422** before upstream.

---

## Command request

Logical view of the **write JSON body** plus path context (same as [Write endpoint (client HTTP)](#write-endpoint-client-http)):

| Field | Type | Notes |
|-------|------|--------|
| `operation` | string | **`operation_id`** from the [writable catalog](#writable-parameter-catalog-initial-subset); must appear in **`BRIDGE_WRITE_ALLOWLIST`** after readonly check. |
| `parameters` | object | Shape defined per operation in the table **Normative `parameters` by `operation`**; serialized to upstream `param1`… |
| `device_sn` | string | From path `{device_sn}`; must match configured device list (FR-020). |

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

## TLX live telemetry (upstream, empirical)

Logical **instantaneous and energy** readouts for TLX inverters. Distinct from [Device parameters (CAP-01)](#device-parameters-cap-01) (`readAllMinParam` / configuration).

### How samples were captured

| Script | Output (under `audit/explore/`) |
|--------|----------------------------------|
| `scripts/explore/fetch_tlx_telemetry.py` | `*_tlx_newTlxApi_system_status.json`, `*_tlx_newTlxApi_energy_overview.json`, optional `*_tlx_*_bdc.json` |

**Programmatic web session** (`newTwoLoginAPI.do` + `JSESSIONID`, same as `tcpSet.do` / `readAllMinParam`):

| Upstream | Role |
|----------|------|
| `POST newTlxApi.do?op=getSystemStatus_KW` with form `plantId`, `id` (= device SN) | Live power, voltages, SoC, mode — **conceptual match** for Shine panel `getTLXStatusData_bdc` |
| `POST newTlxApi.do?op=getEnergyOverview` with same form | Today / cumulative energy (kWh strings) — **conceptual match** for `getTLXTotalData_bdc` |

**Shine panel XHR** (browser `fetch` to `/panel/tlx/getTLXStatusData_bdc` and `getTLXTotalData_bdc` with `tlxSn`):

- With **only** the API login session, the server may respond **302 → `error.do?errorMess=errorNoLogin`** (differs from `tcpSet.do` / `newTlxApi.do`, which accept the same cookies).
- To capture **panel JSON** for diffing against `newTlxApi`, set **`GROWATT_BROWSER_COOKIE`** in `.env` to the full `Cookie` header from DevTools (after loading the logged-in SPA), then re-run the script; optional `*_tlx_*_bdc_follow.json` artifacts record follow-redirect behaviour.

### Response envelope (`newTlxApi`, sampled 2026-04-03)

Top-level keys include: `deviceType`, `msg`, `result`, `dtc`, `haveMeter`, `obj`, `normalPower`, `model`. Values inside `obj` are **strings** (including numerics).

### `getSystemStatus_KW` → `obj` (field labels)

Power fields use the **`unit`** string in `obj` (e.g. `kW`). Labels are inferred from `docs/parameter-glossary.md` naming conventions and live samples; Growatt does not publish a public field spec for this endpoint.

#### State of charge (`SOC*` / `soc*`)

| Key | Label |
|-----|--------|
| `SOC` | Battery state of charge — **primary / display** % (use for a single headline SoC). |
| `soc1` | SoC for **battery module / stack 1** (per-module tracking). |
| `soc2` | SoC for **battery module / stack 2** (often `0` if no second module). |
| `SOC2` | Secondary SoC channel (API naming); aligns with the second reporting path; not a separate “total” from `SOC`. |
| `socType` | Which SoC interpretation the portal uses (**enum** / selector). |

#### Battery charge & discharge power (`chargePower*` / `pdisCharge*`)

These are **battery DC paths**, not PV. **`chargePower`** is the aggregate; **`chargePower1` / `chargePower2`** split by path or module. **`pdisCharge`** is aggregate discharge; **`pdisCharge1` / `pdisCharge2`** split the same way.

| Key | Label |
|-----|--------|
| `chargePower` | Total **battery charge** power (all paths). |
| `chargePower1` | Charge power on **path / module 1**. |
| `chargePower2` | Charge power on **path / module 2**. |
| `pdisCharge` | Total **battery discharge** power. |
| `pdisCharge1` | Discharge power on **path / module 1**. |
| `pdisCharge2` | Discharge power on **path / module 2**. |

#### PV strings (keep separate)

| Key | Label |
|-----|--------|
| `vPv1` … `vPv4` | **PV string 1–4 DC voltage** (V). |
| `pPv1` … `pPv4` | **PV string 1–4 DC power** (in `unit`). |
| `ppv` | **Total PV power** (sum of strings in this snapshot). |

#### Grid, load, and AC

| Key | Label |
|-----|--------|
| `pac` | **AC power** (inverter AC port / output; convention matches glossary `pac`). |
| `pLocalLoad` | **Local load** power. |
| `pactouser` | **Grid → user / import** power. |
| `pactogrid` | **Inverter → grid / export** power. |
| `vac1` / `vAc1` | **Grid AC voltage** (L1); duplicate casing for the same measurement. |
| `fAc` | **Grid AC frequency** (Hz). |
| `upsVac1` / `upsFac` | **UPS / backup** AC voltage & frequency (often `0` when inactive). |

#### Other `obj` keys (sampled payloads)

| Key | Label |
|-----|--------|
| `tbModuleNum` | **Number of battery modules** / stacks reported. |
| `vBat` | **Battery bus voltage** (HV pack side, as reported). |
| `bMerterConnectFlag` | **Grid meter connected** flag (API typo “Merter”). |
| `priorityChoose` | **Energy priority** mode (**enum**). |
| `pex` | **External / auxiliary DC power** (Growatt uses `pex*` for EX ports on some products; confirm for TLX if metering-critical). |
| `lost` | **Localization / status token** (e.g. `tlx.status.checking`) — not a numeric power. |
| `dType` | **Device subtype** code (internal). |
| `deviceType` | **Device type** code (may differ from plant list APIs — see glossary). |
| `isRefreshBtnShow` | **Portal UI**: show manual refresh. |
| `unit` | **Power unit** for `p*` fields (e.g. `kW`). |
| `bmsBatteryEnergy` | **BMS battery energy** string (often cumulative, includes unit suffix in value). |
| `status` | **High-level device status** code. |
| `pmax` | **Rated / max AC power** capability. |
| `uwSysWorkMode` | **System work mode** (**enum**). |
| `prePto` | **Pre–permission-to-operate** / interconnection staging flag. |
| `operatingMode` | **Operating mode** (**enum**). |
| `wBatteryType` | **Battery product / chemistry** family code. |
| `invStatus` | **Inverter status** / fault class code. |
| `bdcStatus` | **Battery DC converter (BDC)** status. |
| `isMasterOne` | **Multi-inverter: master** flag. |

#### Label caveats

- **`SOC` vs `soc1` / `soc2`:** use **`SOC`** for one user-facing %; use **`soc1` / `soc2`** for per-module views.
- **`chargePower*` vs `pPv*`:** totals vs **string** powers — do not merge PV strings into battery charge fields.

### `getEnergyOverview` → `obj` (labels)

Values are **strings** (often kWh). Names follow cumulative / “today” patterns in `parameter-glossary.md` §3.4.

| Key | Label |
|-----|--------|
| `epvToday` | **PV energy generated today**. |
| `epvTotal` | **PV energy generated** (lifetime). |
| `elocalLoadToday` | **Local load energy today**. |
| `elocalLoadTotal` | **Local load energy** (lifetime). |
| `echargetoday` | **Battery charge energy today** (note casing). |
| `echargetotal` | **Battery charge energy** (lifetime). |
| `edischargeToday` | **Battery discharge energy today**. |
| `edischargeTotal` | **Battery discharge energy** (lifetime). |
| `etoGridToday` | **Energy to grid today** (export). |
| `etogridTotal` | **Energy to grid** (lifetime export). |
| `isMasterOne` | **Multi-inverter: master** flag (when present on overview). |

**Bridge direction:** Prefer **`newTlxApi.do`** for normalized telemetry in the redesigned API unless a requirement explicitly mirrors Shine panel widgets fed only by `getTLX*Data_bdc`.

### Downstream TLX telemetry (keys passed to clients)

The bridge **does not** forward the full `obj` from either upstream call. For TLX, the **only** upstream fields that may populate the downstream telemetry contract are listed below. All other keys documented in the **`getSystemStatus_KW`** and **`getEnergyOverview`** field tables above remain **diagnostic / exploratory** unless this list is extended by spec.

**Instantaneous** (from `getSystemStatus_KW` → `obj`; power magnitudes follow `unit`, typically kW as strings):

| Upstream key | Role |
|--------------|------|
| `SOC` | Battery state of charge (headline %) |
| `chargePower` | Total battery **charge** power |
| `pdisCharge` | Total battery **discharge** power |
| `ppv` | Total **PV** power |
| `pactouser` | Grid → user (**import**) power |
| `pactogrid` | Inverter → grid (**export**) power |
| `pLocalLoad` | **Local load** power |

**Energy today** (from `getEnergyOverview` → `obj`; values are strings, typically kWh):

| Upstream key | Role |
|--------------|------|
| `epvToday` | PV energy **today** |
| `elocalLoadToday` | Local load energy **today** |
| `echargetoday` | Battery charge energy **today** (preserve upstream casing) |
| `edischargeToday` | Battery discharge energy **today** |
| `etoGridToday` | Energy to grid **today** (export) |

**Out of scope for this downstream set:** per-string PV (`pPv1`…`pPv4`, `vPv1`…`vPv4`), split charge/discharge (`chargePower1`/`2`, `pdisCharge1`/`2`), `soc1`/`soc2`, and **lifetime** counters on `getEnergyOverview` (`epvTotal`, `elocalLoadTotal`, `echargetotal`, `edischargeTotal`, `etogridTotal`, etc.) unless a future spec change adds them.

**Sampling cadence:** Upstream status is treated as **~5 minute** resolution; downstream responses should respect the same freshness window (see implementation plan: cache / rate alignment).

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
