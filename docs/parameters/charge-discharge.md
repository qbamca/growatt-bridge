# Battery Charge and Discharge Power Rates

**Applies to:** Growatt MOD 12KTL3-HU + APX5 P2 battery (MIN/TLX family, device type 7)

---

## What it controls

Two independent **power rate limiters** cap how fast the inverter moves energy into and out of the battery, expressed as a percentage of the battery system's rated charge/discharge power.

These are **throttles, not targets.** The inverter still uses its normal control logic (TOU mode, SOC thresholds, PV availability) to decide *when* to charge or discharge — the power rate only sets the upper bound on *how fast*.

### Charge power rate (`set_charge_power`)

Limits the maximum rate at which energy flows from PV (or grid, during AC charge) **into** the APX5 P2 battery. At 100%, the inverter uses the full rated charge capability of the BDC module. At 50%, it halves that rate.

Physical effect:
- Reduces peak current into the battery cells
- Smooths out charge bursts from high-PV midday conditions
- Does not directly limit PV output — excess PV beyond the throttled charge rate still feeds loads and exports

### Discharge power rate (`set_discharge_power`)

Limits the maximum rate at which energy flows from the APX5 P2 battery **to loads and/or grid**. At 100%, the inverter uses the full rated discharge capability. At 50%, it halves peak discharge current.

Physical effect:
- Limits battery contribution to load spikes
- The gap between load demand and throttled battery output is filled by grid import
- Does not affect PV-to-load routing (PV still supplies loads directly at full power)

---

## API mapping

### `set_charge_power`

| Item | Value |
|------|-------|
| Bridge operation ID | `set_charge_power` |
| growattServer method | `min_write_parameter(device_sn, "pv_active_p_rate", value)` |
| Growatt parameter ID | `pv_active_p_rate` |
| API value type | Integer string (`"0"` – `"100"`) |
| Config read field | `charge_power_rate` in `NormalizedConfig` / `chargePowerCommand` in raw `tlxSetbean` |

**Request body:**

```json
{
  "params": {
    "value": 80
  }
}
```

### `set_discharge_power`

| Item | Value |
|------|-------|
| Bridge operation ID | `set_discharge_power` |
| growattServer method | `min_write_parameter(device_sn, "grid_first_discharge_power_rate", value)` |
| Growatt parameter ID | `grid_first_discharge_power_rate` |
| API value type | Integer string (`"0"` – `"100"`) |
| Config read field | `discharge_power_rate` in `NormalizedConfig` / `disChargePowerCommand` in raw `tlxSetbean` |

**Request body:**

```json
{
  "params": {
    "value": 75
  }
}
```

---

## Valid ranges

| Parameter | Min | Max | Notes |
|-----------|-----|-----|-------|
| `value` (charge) | 0 | 100 | Percentage of rated charge power |
| `value` (discharge) | 0 | 100 | Percentage of rated discharge power |

**Boundary notes:**

- **`0`:** Sets the rate to zero. Effectively **disables charging or discharging** at the API level. The inverter will not move energy in that direction regardless of TOU mode or SOC. Only set to 0 deliberately (e.g. to pause discharge during a specific period); restore to a working value when done.
- **`100`:** Full rated power. For the MOD 12KTL3-HU + APX5 P2, the BDC (Battery DC Converter) rated charge/discharge power determines the physical maximum — `100%` does not exceed hardware limits, it simply removes the software throttle.
- Non-zero values below ~10% may result in the inverter rounding to its minimum controllable power step; behaviour at very low values is firmware-dependent.

---

## Default values (factory / post-reset)

As observed on `TSS1F5M04Y`:

| Parameter | Raw field | Observed value | Meaning |
|-----------|-----------|----------------|---------|
| Charge power rate | `chargePowerCommand` | `100` | Full rated charge power — no throttle |
| Discharge power rate | `disChargePowerCommand` | `100` | Full rated discharge power — no throttle |

Factory default for both is `100` (unrestricted). This is the safe operating default.

---

## Current value — how to read it

```
GET /api/v1/devices/{sn}/config
```

Response includes:

```json
{
  "charge_power_rate": 100,
  "discharge_power_rate": 100
}
```

These map to `tlxSetbean.chargePowerCommand` and `tlxSetbean.disChargePowerCommand` in the raw `min_detail` response.

---

## Dependencies

- **Battery present:** Both parameters are meaningless without a connected battery module. The APX5 P2 must be online and communicating with the BDC.
- **TOU mode:** The power rate caps apply within whatever TOU mode is active. If the active segment is load-first (mode 0) and PV is insufficient, the battery will discharge up to `discharge_power_rate` to cover the deficit. If mode is battery-first, the inverter actively discharges up to `discharge_power_rate` to cover loads.
- **BDC hardware limit:** The APX5 P2 / BDC combination has a hardware maximum charge/discharge rate independent of these settings. The `100%` software limit maps to that hardware maximum. A value above 100% is rejected by the bridge.

---

## Risk level

**Low** for values between 10–100%.

**Medium** for setting either rate to 0%:

- Charge at 0%: battery never charges. If PV or AC is the only power source and loads exceed PV, battery remains at current SOC and grid fills the gap. The battery will slowly self-discharge with no replenishment — risk of deep discharge if this persists.
- Discharge at 0%: battery never discharges to loads. Grid covers all load deficit. No hardware risk, but billing impact may be significant. Restoring to a working value re-enables battery use.

Neither setting can cause immediate hardware damage, but persistent `0%` discharge rate combined with AC charge active wastes energy cycling through the grid.

---

## Example

**Scenario:** Reducing battery cycling during very hot weather to extend cell longevity.

**Before:**
```json
{"charge_power_rate": 100, "discharge_power_rate": 100}
```

**Action — throttle both to 60% of rated:**

```http
POST /api/v1/devices/TSS1F5M04Y/commands/set_charge_power
{"params": {"value": 60}}

POST /api/v1/devices/TSS1F5M04Y/commands/set_discharge_power
{"params": {"value": 60}}
```

**After:**
```json
{"charge_power_rate": 60, "discharge_power_rate": 60}
```

**Effect:** Peak charge/discharge current drops by 40%. Battery temperature rise during charge/discharge cycles is reduced. PV excess beyond the throttled charge rate exports to grid instead.

---

## Readback behaviour

Post-write readback for these operations uses the Growatt OpenAPI V1 `min_detail` endpoint. Direct per-parameter readback is not available in the V1 API — the bridge reads the full device config and extracts the relevant field. The `readback` section in the response will typically show `readback_failed: true` with a note that verification must be done via `GET /config`.

Verify via:

```
GET /api/v1/devices/{sn}/config
```

Check `charge_power_rate` and `discharge_power_rate` match the sent values.

---

## See also

- [time-segments.md](time-segments.md) — TOU modes that drive when charge/discharge occurs
- [battery-policy.md](battery-policy.md) — SOC boundaries that stop charge/discharge
- [safety-constraints.md](safety-constraints.md) — parameters that must not be touched
