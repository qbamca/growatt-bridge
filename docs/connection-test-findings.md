# Connection Test Findings (2026-03-28)

Observations from running `scripts/test_connection.py` against the live Growatt OpenAPI V1 with a real MOD 12KTL3-HU / APX5 P2 system (`TSS1F5M04Y`, plant `10581915`).

## Environment

- growattServer 2.0.1
- Server: `https://openapi.growatt.com/`
- Device type reported by `device_list`: **7** (MIN/TLX)
- Device type reported by `device_detail`: **6** (maps to UNKNOWN in our code)

---

## 1. `min_read_time_segment` does not exist in growattServer 2.0.1

**Symptom:** `client.read_time_segments()` fails with `AttributeError: 'OpenApiV1' object has no attribute 'min_read_time_segment'`.

**Impact:** `GET /config/time-segments` and the TOU portion of `GET /config` will 502 or return empty. Any future bridge TOU write would lack readback until this is fixed.

**Root cause:** `GrowattClient.read_time_segments()` at `client.py:162` calls `self._api.min_read_time_segment(device_sn)`, but that method doesn't exist in growattServer 2.0.1.

**Where the data actually is:** The TOU schedule IS present in the `min_detail` response, nested under `tlxSetbean.yearTime1` through `yearTime9`. Each value is a packed string like `"2_0_6_0_10_50_1"`, likely encoding `mode_?_startHH_startMM_endHH_endMM_enabled`.

**Fix path:**

1. In `client.py`, change `read_time_segments()` to call `self._api.min_detail(device_sn)` and extract `tlxSetbean.yearTimeN` fields.
2. In `config_read.py`, add a parser for the `"mode_?_HH_MM_HH_MM_enabled"` packed format into `TimeSegment` objects.
3. Test with the real packed values observed:
  - `yearTime1 = "2_0_6_0_10_50_1"` → segment 1, mode 2 (grid-first), 06:00–10:50, enabled
  - `yearTime2 = "0_0_22_0_30_0_0"` → segment 2, mode 0, 22:00–?? (needs format analysis), disabled
  - `yearTime3 = "2_0_18_30_20_0_1"` → segment 3, mode 2, 18:30–20:00, enabled
  - `yearTime4 = "0_0_20_1_22_0_1"` → segment 4, mode 0, 20:01–22:00, enabled
  - `yearTime5..9 = "0_0_0_0_0_0_0"` → unused (all zeros)

**Also note:** The `forcedTimeStart1..9` / `forcedTimeStop1..9` / `forcedStopSwitch1..9` fields in `tlxSetbean` appear to be a parallel set of forced-discharge time windows. These were observed as:

- `forcedTimeStart1="4:0"`, `forcedTimeStop1="6:0"`, `forcedStopSwitch1=1` (enabled)
- `forcedTimeStart2="14:0"`, `forcedTimeStop2="15:0"`, `forcedStopSwitch2=0` (disabled)
- etc.

The relationship between `yearTimeN` and `forcedTimeStartN/StopN` needs investigation — they may control different scheduling behaviors (TOU priority vs forced charge/discharge windows).

---

## 2. `device_detail` returns `deviceType=6`, not 7

**Symptom:** `device_list` returns `type=7` for `TSS1F5M04Y`, but `min_detail` returns `deviceType=6` in the response body.

**Impact:** Currently non-breaking because `detect_device_family()` seeds the family cache from `device_list`, which has the correct type. But if any code path tried to detect family from a `device_detail` response, it would get `UNKNOWN`.

**Where:** `client.py:121` caches from `device_list`, which has `type=7`. The `deviceType=6` inside `min_detail` seems to be Growatt's internal sub-type for this specific hardware variant.

**Fix path:** No immediate fix needed. Just don't add family detection logic that reads `deviceType` from `device_detail` responses — always go through the `device_list`-based cache.

---

## 3. Telemetry lives in `min_energy`, not `min_detail`

**Symptom:** The telemetry route (`telemetry.py:168`) calls `client.device_detail()`, but the live power/energy/SOC values are in the `device_energy()` response, not `device_detail()`.

**What `min_detail` contains:** Device identity, firmware versions, the `tlxSetbean` config blob, and some static info. It does NOT contain `ppv`, `pac`, `soc`, `pCharge`, `pDischarge`, `eToday`, etc.

**What `min_energy` contains (observed):** All the live telemetry fields the `normalize_min_telemetry` function expects:

- `ppv=4971.7`, `ppv1=1542.4`, `ppv3=3429.3` (PV input)
- `pac=6427.7`, `pac1/pac2/pac3` (AC output)
- `vac1=242.7`, `vac2=242.2`, `vac3=243.6` (AC voltages)
- `iac1/iac2/iac3=8.6` (AC currents)
- `fac=49.95` (grid frequency)
- `bdc1Soc=78`, `bmsSoc=78` (battery SOC)
- `pCharge=0`, `bdc1DischargePower=1492` (battery power)
- `echargeToday=14`, `edischargeToday=8.9` (energy counters)
- `etoGridToday=0`, `etoUserToday=21.8` (grid exchange)
- `temp1=48.8`, `temp2=65.8` (temperatures)
- `lost=true` (see finding 4)

**Field name mismatches in `normalize_min_telemetry`:**
The function tries `soc`, `batterySOC`, `bdc1_SOC` — but the actual field names are `bdc1Soc` / `bmsSoc`. Similar mismatches for:

- charge: `pCharge` exists ✓ (already listed)
- discharge: `bdc1DischargePower` (not `pDisCharge` or `pDischarge` or `dischargePower`)
- energy: `echargeToday`/`edischargeToday` (not `eBatChargeToday`)
- grid: `etoGridToday`/`etoUserToday` (not `eToGridToday`)

**Fix path:**

1. `telemetry.py:168` — call `client.device_energy(device_sn, family)` instead of `client.device_detail(...)`.
2. Update `normalize_min_telemetry()` field aliases to include the actual camelCase names from `min_energy`: `bdc1Soc`, `bmsSoc`, `bdc1DischargePower`, `bdc1ChargePower`, `echargeToday`, `edischargeToday`, `etoGridToday`, `etoUserToday`, `elocalLoadToday`.
3. Consider merging both `min_detail` and `min_energy` into the raw dict for maximum field coverage.

---

## 4. `lost=true` in live `min_energy` response

**Symptom:** `device_energy` returned `"lost": true` for `TSS1F5M04Y` even though live power values were present and the device had `status=1` ("Normal").

**Likely cause:** Growatt's `lost` flag is based on the `last_update_time` timestamp being more than a threshold behind server time. The device was reporting at `:03:12` but the server time was later. This is a known Growatt Cloud quirk — the flag doesn't necessarily mean the device is unreachable.

**Impact:** The `NormalizedTelemetry.lost` field will show `true` even when the device is actively generating and sending data. This could confuse agents or health checks.

**Fix path:** Consider sourcing `lost` from `device_list` (which showed `lost=false`) rather than from `device_energy`. Or derive it from whether critical telemetry fields (ppv, pac) are non-null, as a secondary signal.

---

## 5. Config field mapping needs `tlxSetbean` nesting

**Symptom:** `config_read.py:_build_config()` reads config fields like `ac_charge`, `discharge_stop_soc`, `exportLimit` directly from the top-level raw dict returned by `device_detail`. But those fields are nested inside `tlxSetbean` in the actual response.

**Actual field locations in `min_detail` response:**


| NormalizedConfig field    | Where it is in raw response         | Raw field name           | Observed value |
| ------------------------- | ----------------------------------- | ------------------------ | -------------- |
| `ac_charge_enabled`       | `tlxSetbean.acChargeEnable`         | `acChargeEnable`         | `1`            |
| `ac_charge_stop_soc`      | `tlxSetbean.ubAcChargingStopSOC`    | `ubAcChargingStopSOC`    | `40`           |
| `discharge_stop_soc`      | `tlxSetbean.onGridDischargeStopSOC` | `onGridDischargeStopSOC` | `20`           |
| `charge_power_rate`       | `tlxSetbean.chargePowerCommand`     | `chargePowerCommand`     | `100`          |
| `discharge_power_rate`    | `tlxSetbean.disChargePowerCommand`  | `disChargePowerCommand`  | `100`          |
| `export_limit_enabled`    | `tlxSetbean.exportLimit`            | `exportLimit`            | `1`            |
| `export_limit_power_rate` | `tlxSetbean.activeRate`             | `activeRate`             | `100`          |


**Fix path:**

1. In `config_read.py:_build_config()`, extract the `tlxSetbean` sub-dict from `detail_raw` first: `setbean = detail_raw.get("tlxSetbean", {})`.
2. Read config fields from `setbean` using the actual field names above.
3. Note that the raw field names differ significantly from both the snake_case parameter IDs used in write operations AND from the aliases currently in `_build_config`. Every alias needs verification against this table.

---

## Raw response samples

Full JSON responses are available by re-running `scripts/test_connection.py` — the script prints redacted JSON for every call. The key structures to reference:

- `**plant_list`**: List of dicts with `plant_id`, `name`, `current_power`, `total_energy`, `country`.
- `**device_list**`: List of dicts with `device_sn`, `type` (3=meter, 7=inverter), `model`, `lost`, `status`.
- `**min_detail**`: Large dict — identity fields at top level, config in `tlxSetbean`, battery info in `bdc1*` fields.
- `**min_energy**`: Large dict — all live telemetry (power, voltage, current, energy counters, SOC, temperatures).

