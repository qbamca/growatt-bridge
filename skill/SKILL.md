---
name: growatt-bridge
description: Use the growatt-bridge HTTP API to read Growatt plant/device telemetry and config, and to execute allowlisted named write operations safely. Apply when user wants to know the status of the photovolatic installation and production, and when changes in inverter settings are needed.
---

# growatt-bridge — agent skill

HTTP bridge around **Growatt OpenAPI V1** with a **safety layer**: writes are **named operations only** (no arbitrary `parameter_id`). Default deployment is **read-only** until operators change environment variables.

## When to use

- Discover plants/devices, read telemetry and configuration, or run **documented** write operations through this service.
- Prefer **`GET /docs`** on the running instance for interactive OpenAPI when available.

## When not to use

- Do not invent raw Growatt parameters or bypass the bridge: unsupported writes **cannot** be done through this API by design.
- Grid-code, anti-islanding, and other installer-only parameters are out of scope; see repository `docs/parameters/safety-constraints.md`.

## Base URL and health

- Default listen port **`8081`** (see `docker-compose.yaml`, `BRIDGE_PORT`).
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

**Config gaps:** Growatt often does not return every written parameter on read; `NormalizedConfig` may leave fields **`null`**. Do not assume “null means zero”.

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
| `set_time_segment` | `segment` (integer **1–9**), `mode` (integer **0**=load\_first / **1**=battery\_first / **2**=grid\_first), `start_time` (HH:MM), `end_time` (HH:MM), `enabled` (boolean, default `true`) |

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

## Limitations

- **No raw parameter API** — only registry operations.
- **Writes are MIN-family** in the current registry; other families get **422** on writes.
- **Telemetry** is a best-effort snapshot; fields may be missing; check **`lost`**.
- **Audit log** path **`BRIDGE_AUDIT_LOG`** (default `/var/log/growatt-bridge/audit.jsonl` in containers); not exposed over HTTP; entries never contain the API token.

## Security and risk

- The service has **no built-in HTTP authentication**. Anyone who can reach the bridge can use the server’s Growatt token and policy. Run on a **private network**, **VPN**, or behind a **reverse proxy** with auth.
- **Never** paste **`GROWATT_API_TOKEN`** or web passwords into chat or logs.
- Writes affect **real hardware** (battery, grid, schedules). Treat every successful command as a physical change to the installation.
- **CORS** allows **`*`** and methods **GET/POST** — relevant if a browser can reach the bridge.

## Repository references

- `docs/growatt-cloud-api.md` — upstream API notes.
- `docs/parameters/` — human-oriented guides per topic.
- `docs/parameters/safety-constraints.md` — what must not be changed via agents.
