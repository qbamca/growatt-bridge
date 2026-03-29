# Growatt Cloud API Documentation

Reference for the Growatt OpenAPI V1 used by `growatt-bridge`. Gathered from external sources and validated against a live Growatt MOD 12KTL3-HU installation.

---

## API Variants

| Variant | Base URL | Auth | Notes |
|---------|----------|------|-------|
| Legacy (ShinePhone) | server.growatt.com, openapi.growatt.com | Username + MD5 password, session | Reverse-engineered from mobile app |
| OpenAPI V1 | openapi.growatt.com/v1/ | Token | Official, better security — preferred for growatt-bridge |

## Regional Server URLs

| Region | URL |
|--------|-----|
| Europe (default) | https://openapi.growatt.com/ |
| China | https://openapi-cn.growatt.com/ |
| North America | https://openapi-us.growatt.com/ |

## Authentication

### Legacy
- ShinePhone/dashboard username and password
- Password sent as MD5 hash (passwordCrc)
- Session/cookies maintained after login

### OpenAPI V1
- Token from ShinePhone app: **Me** > account name > **API Token**
- Pass token in Authorization header
- Released 2025, replaces username/password for V1

## Endpoint Catalog (from growattServer)

### Legacy (ShinePhone)

| Method | Args | Description |
|--------|------|-------------|
| login | username, password | Session auth |
| plant_list | user_id | List plants |
| plant_info | plant_id | Plant details |
| device_list | plant_id | Devices in plant |
| mix_info | mix_id, plant_id? | MIX high-level info |
| mix_totals | mix_id, plant_id | MIX daily/total |
| mix_system_status | mix_id, plant_id | MIX real-time status |
| mix_detail | mix_id, plant_id, timespan, date | MIX time-series |

### OpenAPI V1

| Method | Args | Description |
|--------|------|-------------|
| plant_list | — | List plants |
| plant_details | plant_id | Plant details |
| plant_energy_overview | plant_id | Energy overview |
| device_list | plant_id | Devices in plant |
| sph_detail | device_sn | SPH (MIX) device + settings |
| sph_energy | device_sn | SPH current energy |
| sph_energy_history | device_sn, dates... | SPH history (7-day max) |
| min_detail | device_sn | MIN/TLX device info + settings |
| min_energy | device_sn | MIN/TLX current energy snapshot |
| min_energy_history | device_sn, dates... | MIN/TLX history (5-min intervals, 7-day max) |
| min_write_time_segment | device_sn, segment, ... | Write TOU schedule slot |
| min_write_parameter | device_sn, parameter_id, value | Write named parameter (see safety.py allowlist) |

## Device Type Mapping

| Type | Hardware | Legacy | OpenAPI V1 |
|------|----------|--------|------------|
| 7 | MIN/TLX / string or hybrid inverter | tlx_* | min_* |
| 5 | SPH/MIX / hybrid inverter (older) | mix_* | sph_* |
| 2 | Storage (battery, separate device) | storage_* | device/list may include |
| 3 | Other (meter, datalogger) | — | device/list |

**Growatt MOD 12KTL3-HU** (3-phase, 12kW hybrid with BDC battery) → **type 7 / MIN-TLX**. Use `min_*` methods. The `device_list` response confirms `type: 7` for this hardware. Do **not** use `sph_*` (type 5) methods.

**Battery visibility**: Battery data for MIN/TLX hybrids with integrated BDC module is embedded inside `min_detail` and `min_energy` responses (BMS, BDC1, BDC2 fields). It does not appear as a separate type-2 device in `device_list`.

## Rate Limits

OpenAPI V1 has more relaxed rate limiting than Legacy. For `min_energy_history`: 7-day max date range per request for 5-minute interval data (yields up to ~2016 records).

## Verified Behavior

Run `scripts/test_connection.py` to validate connectivity and enumerate live API responses. The script exercises: `plant_list` → `device_list` → `min_detail` → `min_energy` → `min_energy_history` using the configured token. See `docs/parameter-glossary.md` for field-level documentation of actual response values.

### Test / Demo Server

Growatt operates a public demo server at `test.growatt.com` that speaks the same OpenAPI V1 protocol as `openapi.growatt.com`. It can be used to integration-test the bridge without touching a real installation.

| Property | Value |
|----------|-------|
| Base URL | `https://test.growatt.com/` |
| Demo token | `6eb6f069523055a339d71e5b1f6c88cc` (published in Growatt's 2016 developer PDF — not a secret) |
| Protocol | OpenAPI V1 (identical to production) |

The demo account has pre-populated plants and may include demo devices. Read operations work against this data. **Do not send real write commands** to the test server — the demo plant data is shared.

The repo ships a `.env.test` file pre-configured for this server (token, URL, `BRIDGE_READONLY=true`).

**Run the integration probe:**

```bash
python scripts/test_integration.py
# Override server or env file:
python scripts/test_integration.py --env-file /path/to/.env.test --server-url https://test.growatt.com/
# Show full response bodies:
python scripts/test_integration.py --verbose
```

The script boots the bridge in-process (no separate server needed), discovers plants/devices dynamically, exercises every read route, and runs dry-run `/validate` against every write operation. It prints a pass/fail/skip summary table. Exit code 0 = all passed or skipped; 1 = any failure.

**Note on demo token rate limits**: The public 2016 demo token is shared by many developers and may return `error_code: 10012` (`error_frequently_access`) if the token has been called too frequently. When rate-limited, the bridge correctly propagates the upstream failure as HTTP 502 and the script reports the `/api/v1/plants` check as FAIL. Health and info checks still pass. This is expected behavior when the upstream is unavailable.

## OpenAPI `tlxSet` vs legacy `tcpSet.do` (error 10002)

Some plants return **`error_useTrueHostToSet` (10002)** on OpenAPI V1 `POST .../v1/tlxSet` even though reads work. The Shine web portal uses **`POST https://server.growatt.com/tcpSet.do`** with `action=tlxSet`, `serialNum`, a web-specific `type` field, and `param1`…`param19` (time segments use `param1`–`param6` only), plus session cookies after dashboard login.

When **`GROWATT_LEGACY_WEB_MIN_WRITES=true`** (or `BRIDGE_LEGACY_WEB_MIN_WRITES`), the bridge sends **every** allowlisted MIN parameter write and **every** `set_time_segment` through that legacy path instead of OpenAPI. Configure **`GROWATT_WEB_BASE_URL`** (default `https://server.growatt.com/`), **`GROWATT_WEB_USERNAME`**, **`GROWATT_WEB_PASSWORD`** (plain password; hashed like `growattServer.hash_password`), and ensure a **resolved plant ID** (`?plant_id=` on command URLs or `GROWATT_PLANT_ID`). OpenAPI token auth is unchanged for reads and for writes when the flag is off.

### Legacy `tcpSet.do` `type` mapping (MIN writes)

Web `type` strings are **not** the same as OpenAPI `parameter_id`. They are aligned with `tlxSetbean` / portal usage where possible. **Confirm with one DevTools capture per setting** on your plant if a write fails or no-ops.

| Bridge operation | OpenAPI `parameter_id` (unchanged when legacy off) | Web `type` on `tcpSet.do` |
|------------------|----------------------------------------------------|---------------------------|
| `set_ac_charge_stop_soc` | `ac_charge_soc_limit` | `ub_ac_charging_stop_soc` |
| `set_discharge_stop_soc` | `discharge_stop_soc` | `on_grid_discharge_stop_soc` |
| `set_ac_charge_enable` | `ac_charge` | `ac_charge_enable` |
| `set_charge_power` | `pv_active_p_rate` | `charge_power_command` |
| `set_discharge_power` | `grid_first_discharge_power_rate` | `dis_charge_power_command` |
| `set_export_limit` | `export_limit_power_rate` | `export_limit_power_rate` |
| `set_time_segment` | (OpenAPI encodes slot) | `time_segment{N}` where *N* is 1–9 (same shape as growattServer `Min.write_time_segment`) |

## Known Gaps and Limitations

- Token lifetime not officially documented; community reports tokens do not expire if not revoked.
- `error_permission_denied` (10011) occurs when using dashboard (web portal) credentials for the API — use ShinePhone app credentials instead.
- Write operations (`min_write_parameter`) accept arbitrary `parameter_id` values with no upstream validation. The bridge safety layer enforces an explicit allowlist and range checks — never expose raw write methods.
- `deviceType` field in `min_detail` (value `6`) differs from `type` in `device_list` (value `7`) — a known Growatt API inconsistency; use `device_list.type` for routing decisions.
- `min_energy_history` pagination uses `next_page_start_id`; query until this field is absent or `count` records are retrieved.

## External References

See `docs/references.md` for the full index of PDFs and online documentation.
