---
name: growatt-bridge
description: Use the growatt-bridge HTTP API to read Growatt plant/device telemetry and config, and to execute allowlisted named write operations safely. Apply when user wants to know the status of the photovolatic installation and production, and when changes in inverter settings are needed.
---

# growatt-bridge — agent skill

HTTP bridge around **Growatt OpenAPI V1** with a **safety layer**: writes are **named operations only** (no arbitrary `parameter_id`). Default deployment is **read-only** until operators change environment variables.

## When to use

- Discover plants/devices, read telemetry and configuration, or run **documented** write operations through this service.

## When not to use

- Do not invent raw Growatt parameters or bypass the bridge: unsupported writes **cannot** be done through this API by design.
- Grid-code, anti-islanding, and other installer-only parameters are out of scope; see repository `docs/parameters/safety-constraints.md`.

## Base URL and health

- Default listen port **`8081`** (see `docker-compose.yaml`, `BRIDGE_PORT`).
- **`GET /openapi.json`** — machine-readable OpenAPI schema; fetch this when you need exact request/response shapes not covered by this skill.
- **`GET /docs`** — interactive Swagger UI (browser only).
- **`GET /health`** — unauthenticated host connectivity check (DNS/TLS to `GROWATT_SERVER_URL` only, no API call); returns `cloud_reachable` and `status` (`ok` / `degraded`).
- **`GET /info`** — package version, `readonly`, `allowed_write_operations` (parsed allowlist), default device/plant from env.

## Architecture (mental model)

```text
Client → growatt-bridge (HTTP) → SafetyLayer (writes only) → GrowattClient → Growatt Cloud
```

Reads use the server-configured API token. There is **no separate HTTP API key** for agents.

## Read API (typical order)

Optional query parameter **`plant_id`** on device-scoped routes: resolution order is query hint → `GROWATT_PLANT_ID` → scan all plants for the serial.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/plants` | List plants |
| GET | `/api/v1/plants/{plant_id}` | Plant detail |
| GET | `/api/v1/plants/{plant_id}/devices` | Devices in plant |
| GET | `/api/v1/devices/{device_sn}` | Device identity + family |
| GET | `/api/v1/devices/{device_sn}/capabilities` | Supported read/write **for this device** |
| GET | `/api/v1/devices/{device_sn}/telemetry` | Normalized live snapshot |
| GET | `/api/v1/devices/{device_sn}/config` | Config + TOU segments (MIN); many scalar fields may be `null` |
| GET | `/api/v1/devices/{device_sn}/config/time-segments` | TOU slots only (MIN) |

**Families:** **`capabilities`** lists `supported_read_operations`. **MIN** includes `config` and `config/time-segments`; **SPH** does not list those. Wrong family → **`422`**.

**Config gaps:** Growatt often does not return every written parameter on read; `NormalizedConfig` may leave fields **`null`**. Treat `null` as **unknown/unavailable** — do not substitute `0` or any default value.

## Write discovery

1. **`GET /api/v1/write-operations`** — Full **catalog** of operation IDs, descriptions, `params_schema`, and `constraints` (static, from code). Optional query **`include_policy=true`** adds per-operation **`currently_permitted`** plus server **`readonly`** and **`allowlist_parse_error`** if the allowlist env is invalid.
2. **`GET /api/v1/devices/{device_sn}/capabilities`** — Intersection of **allowlist**, **not readonly**, and **device family**.
3. **`POST /api/v1/devices/{device_sn}/commands/{operation_id}/validate`** — Body `{"params":{...}}`. **No side effects**, no write rate limit.
4. **`POST /api/v1/devices/{device_sn}/commands/{operation_id}`** — Real write. Check **`success`**, **`error`**, **`readback`**, **`audit_id`**.

## Write operations (summary)

The shipped binary only registers operations that have been **integration-tested**. Exact shapes are in **`GET /api/v1/write-operations`** and `src/growatt_bridge/safety.py` (`OPERATION_REGISTRY`).

| operation_id | Params (body `params`) |
|--------------|-------------------------|
| `set_ac_charge_enable` | `enabled` (boolean) — enable or disable AC (grid-to-battery) charging |
| `set_ac_charge_stop_soc` | `value` (integer **10–100**) — SOC target at which AC (grid) charging stops |
| `set_on_grid_discharge_stop_soc` | `value` (integer **10–100**) — SOC at which on-grid discharging stops |
| `set_time_segment` | `segment` (integer **1–9**), `mode` (see below), `start_time` (HH:MM), `end_time` (HH:MM), `enabled` (boolean, default `true`) |

`mode` values for `set_time_segment`:

| Value | Name | Meaning |
|-------|------|---------|
| `0` | `load_first` | PV → load → battery → grid |
| `1` | `battery_first` | PV + battery → load; grid not used |
| `2` | `grid_first` | Grid charges battery; PV → load |

New operations may be added to the registry after integration testing; unregistered `operation_id` values return **404**.

## Environment gates (writes)

- **`BRIDGE_READONLY`** default **`true`** → writes return **`403`**.
- **`BRIDGE_WRITE_ALLOWLIST`** — comma-separated operation IDs; **empty** → no writes even if not readonly.
- **`BRIDGE_RATE_LIMIT_WRITES`** — default **3 per 60s**, in-memory (resets on restart) → **`429`**.
- **`BRIDGE_REQUIRE_READBACK`** — default **`true`**; re-reads config after every successful write and attaches a diff to the response. Many scalar parameters **cannot** be verified via OpenAPI → **`readback_failed`** does **not** imply the write failed.
- **Legacy web writes** (`BRIDGE_LEGACY_WEB_MIN_WRITES` / `GROWATT_LEGACY_WEB_MIN_WRITES`): require **`GROWATT_WEB_USERNAME`**, **`GROWATT_WEB_PASSWORD`**, and resolved **`plant_id`**.

## HTTP status codes (writes)

| Code | Meaning |
|------|---------|
| 403 | Readonly or operation not allowlisted |
| 404 | Unknown `operation_id` |
| 422 | Validation error or unsupported device family |
| 429 | Write rate limit |
| 502 | Cloud / family detection failure |

## Telemetry response fields

`GET /api/v1/devices/{device_sn}/telemetry` returns a normalized snapshot. All power values in **W**, energy in **kWh**, voltage in **V**, current in **A**, frequency in **Hz**, SOC in **%**, temperature in **°C**. Fields are `null` when absent from the Growatt response.

Raw Growatt key names (from `newTlxApi.do?op=getTlxDetailData`):

| Normalized field | Raw Growatt key | Description |
|---|---|---|
| `ppv` | `ppv` | Total PV input power |
| `vpv1` / `vpv2` | `vpv1` / `vpv2` | PV string 1/2 voltage |
| `ipv1` / `ipv2` | `ipv1` / `ipv2` | PV string 1/2 current |
| `pac` | `pac` | Total AC output power |
| `vac1/2/3` | `vac1` / `vac2` / `vac3` | AC phase 1/2/3 voltage |
| `iac1/2/3` | `iac1` / `iac2` / `iac3` | AC phase 1/2/3 current |
| `fac` | `fac` | Grid frequency |
| `soc` | `bdc1Soc` | Battery state of charge (BDC module 1) |
| `p_charge` | `bdc1ChargePower` | Battery charge power |
| `p_discharge` | `bdc1DischargePower` | Battery discharge power |
| `v_bat` | `bdc1Vbat` | Battery voltage |
| `i_bat` | `bdc1Ibat` | Battery current (negative = discharging) |
| `p_to_grid` | `pacToGridTotal` | Power exported to grid |
| `p_to_user` | `pacToUserTotal` | Power imported from grid |
| `e_today` | `eacToday` | AC energy generated today |
| `e_total` | `eacTotal` | Total AC energy generated |
| `e_charge_today` | `echargeToday` | Battery energy charged today |
| `e_discharge_today` | `edischargeToday` | Battery energy discharged today |
| `e_to_grid_today` | `etoGridToday` | Energy exported to grid today |
| `e_from_grid_today` | `etoUserToday` | Energy imported from grid today |
| `temp1` | `temp1` | Inverter temperature sensor 1 |
| `temp2` | `temp2` | Inverter temperature sensor 2 |
| `status_code` | `status` | Raw inverter status integer |
| `status_text` | `statusText` | Human-readable status (`Normal`, `Standby`, `Fault`, …) |
| `lost` | `lost` | `true` when device is offline per cloud |

## Examples

All examples use device `TSS1F5M04Y` (MIN family). Verified against a live bridge instance.

### GET /api/v1/devices/{device_sn}/telemetry

```
GET /api/v1/devices/TSS1F5M04Y/telemetry
```

```json
{
  "device_sn": "TSS1F5M04Y",
  "timestamp": "2026-04-04T20:56:28.006806Z",
  "ppv": 0.0,
  "vpv1": 44.5,
  "vpv2": 0.0,
  "pac": 313.3,
  "vac1": 236.1, "vac2": 242.1, "vac3": 239.5,
  "iac1": 1.1,  "iac2": 1.1,  "iac3": 1.1,
  "fac": 50.02,
  "soc": 30.0,
  "p_charge": 0.0,
  "p_discharge": 469.0,
  "v_bat": 749.0,
  "i_bat": -0.7,
  "p_to_grid": 0.0,
  "p_to_user": 0.0,
  "e_today": 30.4,
  "e_total": 1873.2,
  "e_charge_today": 11.9,
  "e_discharge_today": 21.1,
  "e_to_grid_today": 0.1,
  "e_from_grid_today": 1.0,
  "temp1": 33.3,
  "temp2": 56.3,
  "status_code": 1,
  "status_text": "Normal",
  "lost": true
}
```

### GET /api/v1/devices/{device_sn}/config

```
GET /api/v1/devices/TSS1F5M04Y/config
```

```json
{
  "device_sn": "TSS1F5M04Y",
  "timestamp": "2026-04-04T21:00:10.091949Z",
  "charge_power_rate": 100,
  "discharge_power_rate": 100,
  "discharge_stop_soc": 10,
  "ac_charge_enabled": true,
  "ac_charge_stop_soc": 42,
  "export_limit_enabled": true,
  "export_limit_power_rate": 0,
  "time_segments": [
    {"segment": 1, "mode": 1, "start_time": "05:30", "end_time": "06:00", "enabled": true},
    {"segment": 2, "mode": 1, "start_time": "14:00", "end_time": "15:00", "enabled": false}
  ]
}
```

### POST …/commands/{operation_id}/validate (readonly bridge — validate returns policy error)

When `BRIDGE_READONLY=true`, `/validate` reports the gate as an error even though parameters are well-formed:

```
POST /api/v1/devices/TSS1F5M04Y/commands/set_ac_charge_stop_soc/validate
Content-Type: application/json

{"params": {"value": 80}}
```

```json
{
  "valid": false,
  "operation": "set_ac_charge_stop_soc",
  "device_sn": "TSS1F5M04Y",
  "params": {"value": 80},
  "errors": [
    "Bridge is in readonly mode (BRIDGE_READONLY=true). Set BRIDGE_READONLY=false and configure BRIDGE_WRITE_ALLOWLIST to enable writes."
  ]
}
```

When writes are permitted, a passing validation returns `"valid": true` with `"errors": []`.

### POST …/commands/{operation_id} (successful scalar write, writes-enabled bridge)

Scalar operations (`set_ac_charge_stop_soc`, `set_ac_charge_enable`, `set_on_grid_discharge_stop_soc`) always return `readback_failed: true` — Growatt OpenAPI V1 has no individual parameter read endpoint. **This does not mean the write failed.** Verify via `GET /config`.

`params_sent` includes internal routing fields (`_parameter_id`, `_api_value`, `_legacy_web_type`); ignore these.

```
POST /api/v1/devices/TSS1F5M04Y/commands/set_ac_charge_stop_soc
Content-Type: application/json

{"params": {"value": 80}}
```

```json
{
  "success": true,
  "operation": "set_ac_charge_stop_soc",
  "device_sn": "TSS1F5M04Y",
  "params_sent": {
    "value": 80,
    "_parameter_id": "ac_charge_soc_limit",
    "_api_value": "80",
    "_legacy_web_type": "ub_ac_charging_stop_soc"
  },
  "raw_response": {"result_code": "1", "result_msg": ""},
  "readback": {
    "changed": {},
    "unchanged": [],
    "readback_failed": true,
    "readback_error": "Direct readback of parameter 'ac_charge_soc_limit' is not available via Growatt OpenAPI V1. The write was dispatched successfully — verify via GET /config."
  },
  "audit_id": "a3f1c2d4-...",
  "error": null
}
```

### POST …/commands/set_time_segment (successful write)

`set_time_segment` readback reads the segment back; `changed` uses field names as keys.

```
POST /api/v1/devices/TSS1F5M04Y/commands/set_time_segment
Content-Type: application/json

{"params": {"segment": 1, "mode": 1, "start_time": "22:00", "end_time": "06:00", "enabled": true}}
```

```json
{
  "success": true,
  "operation": "set_time_segment",
  "device_sn": "TSS1F5M04Y",
  "params_sent": {"segment": 1, "mode": 1, "start_time": "22:00", "end_time": "06:00", "enabled": true},
  "raw_response": {"result_code": "1", "result_msg": ""},
  "readback": {
    "changed": {
      "start_time": {"before": null, "after": "22:00"}
    },
    "unchanged": ["mode", "end_time", "enabled"],
    "readback_failed": false,
    "readback_error": null
  },
  "audit_id": "b7e9d0f2-...",
  "error": null
}
```

## Limitations

- **No raw parameter API** — only registry operations.
- **Writes are MIN-family** in the current registry; other families get **422** on writes.
- **Telemetry** is a best-effort snapshot; fields may be missing; check **`lost`**.

## Security and risk

- The service has **no built-in HTTP authentication**. Anyone who can reach the bridge can use the server’s Growatt token and policy. Run on a **private network**, **VPN**, or behind a **reverse proxy** with auth.
- **Never** paste **`GROWATT_API_TOKEN`** or web passwords into chat or logs.
- Writes affect **real hardware** (battery, grid, schedules). Treat every successful command as a physical change to the installation.
- **CORS** allows **`*`** and methods **GET/POST** — relevant if a browser can reach the bridge.

## Repository references

- `docs/growatt-cloud-api.md` — upstream API notes.
- `docs/parameters/` — human-oriented guides per topic.
- `docs/parameters/safety-constraints.md` — what must not be changed via agents.
