# Export Power Limit

**Applies to:** Growatt MOD 12KTL3-HU + APX5 P2 battery (MIN/TLX family, device type 7)

---

## What it controls

The export limit constrains how much power the inverter is allowed to push back into the distribution grid. It is the primary tool for complying with grid operator requirements or local regulations that cap solar export (e.g. a maximum feed-in power agreed with the DSO at installation time).

When enabled and active:

1. The inverter reads real-time grid import/export power from a **physical Growatt meter** connected via RS485.
2. It compares the measured export against the configured limit.
3. If export is approaching or exceeding the limit, the inverter **throttles its AC output** — reducing PV generation and/or battery discharge — to stay within the cap.
4. Surplus PV power that cannot be exported is wasted (curtailed). It does not automatically redirect to battery charging unless a compatible TOU mode is also active.

**This feature requires hardware.** It cannot function using software alone.

---

## Hardware requirement — physical export meter

> **WARNING:** Enabling the export limit (`set_export_limit`) without a correctly installed and communicating Growatt meter will cause the inverter to fault or behave erratically. The bridge enforces acknowledgment of this requirement before accepting the write.

### Required meter hardware

| System type | Required meter | Interface |
|------------|----------------|-----------|
| 3-phase (MOD 12KTL3-HU) | **Growatt TPM** (Three-Phase Meter) | RS485, Modbus RTU |
| Single-phase | Growatt SPM (not applicable here) | RS485, Modbus RTU |

The TPM is a CT (Current Transformer) clamp meter that clips around the main grid feed cables at the meter/distribution board. It measures real-time import and export current on all three phases simultaneously and reports to the inverter over the RS485 bus shared with the ShineWiFi/LAN datalogger.

### RS485 wiring

The TPM connects to the inverter's RS485 port (typically labelled "Meter" or shared with the battery BMS bus depending on inverter revision). Polarity (A+/B-) matters. Check the MOD 12KTL3-HU installation manual for the correct port and pinout.

### Meter failure fallback (`backflowDefaultPower`)

If the TPM loses RS485 communication while export limiting is active, the inverter no longer has real-time export data. The `backflowDefaultPower` parameter defines the maximum output power in this failure state:

- `0 W` (recommended): inverter reduces output to near-zero when meter fails — safest for grid compliance, worst for self-consumption.
- Non-zero: inverter continues generating up to N watts even without meter feedback — risks exceeding grid operator export limit during meter fault.

The `backflowDefaultPower` field is currently `0` on `TSS1F5M04Y` (see [parameter-glossary.md](../parameter-glossary.md)). Do not change it without understanding the grid operator's fault-mode requirements.

### Phase-level control (`backFlowSingleCtrl`)

For 3-phase systems, controls whether the limit is enforced per-phase or on the total system sum:

- `0` (disabled, **correct for Poland**): total/system-level assessment. The inverter sums all three phases. If L1 exports 3 kW but L2 imports 1 kW, net measured export is 2 kW. This is the standard for most EU markets including Poland (EN 50549 framework).
- `1` (enabled): per-phase enforcement. Each phase is independently capped. Required in some countries (e.g. Czech Republic) where per-phase zero-export is mandated.

Do not change `backFlowSingleCtrl` via raw API calls — it is not exposed through the bridge and must only be changed through the Growatt ShineServer web portal after confirming the local grid operator's requirements.

---

## API mapping

### `set_export_limit`

| Item | Value |
|------|-------|
| Bridge operation ID | `set_export_limit` |
| growattServer method | `min_write_parameter(device_sn, "export_limit_power_rate", value)` |
| Growatt parameter ID | `export_limit_power_rate` |
| API value type | Integer string (`"0"` – `"100"`) |
| Config read field | `export_limit_power_rate` in `NormalizedConfig` / `exportLimitPowerRate` in raw `tlxSetbean` |
| Enable/disable field | `exportLimit` in raw `tlxSetbean` (1=enabled, 0=disabled) — not separately settable via bridge |

**The bridge requires `meter_acknowledged: true` in the request.** This is a mandatory safety gate. Omitting it returns a 422 error without touching the hardware.

**Request body:**

```json
{
  "params": {
    "value": 50,
    "meter_acknowledged": true
  }
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `value` | integer | yes | Export cap as % of inverter rated power (0–100) |
| `meter_acknowledged` | boolean | yes | Must be `true` to confirm a physical Growatt TPM meter is installed and communicating |

---

## Valid ranges

| Parameter | Min | Max | Notes |
|-----------|-----|-----|-------|
| `value` | 0 | 100 | Percentage of inverter rated AC output (12 kW for MOD 12KTL3-HU) |

**Conversion examples for MOD 12KTL3-HU (12 kW rated):**

| `value` | Effective export cap |
|---------|---------------------|
| `0` | 0 W — zero export (any surplus diverted/curtailed) |
| `25` | 3,000 W (3 kW) |
| `50` | 6,000 W (6 kW) |
| `75` | 9,000 W (9 kW) |
| `100` | 12,000 W (12 kW) — effectively no cap at rated power |

**Boundary notes:**

- `0` means zero-export mode. The inverter will not push any power to the grid. PV output is curtailed to exactly match local load consumption. This is a valid and safe setting when the TPM is installed.
- `100` at rated capacity means the limit is set to the inverter's maximum — the meter is still active and measuring, but the cap is never reached under normal operation.
- The Growatt API always stores this as a percentage of rated power, regardless of whether the ShineServer UI was set to "Percent" or "Power" mode. The bridge uses percentage exclusively.

---

## Default values (factory / post-reset)

As observed on `TSS1F5M04Y` (2026-02-22), no export meter is installed:

| Raw field | Value | Meaning |
|-----------|-------|---------|
| `exportLimit` | `0` | Export limiting **disabled** |
| `exportLimitPowerRate` | `0` | 0% threshold (dormant) |
| `backflowDefaultPower` | `0` | 0 W fallback on meter failure |
| `backFlowSingleCtrl` | `0` | Total system-level assessment |

The feature is entirely off by default. Enabling it requires both hardware installation and API configuration.

---

## Current value — how to read it

```
GET /api/v1/devices/{sn}/config
```

Response includes:

```json
{
  "export_limit_enabled": false,
  "export_limit_power_rate": 0
}
```

`export_limit_enabled` maps to `exportLimit` in the raw `tlxSetbean`. `export_limit_power_rate` maps to `exportLimitPowerRate`.

Note: The bridge `set_export_limit` operation sets the **rate value** but does not separately toggle the `exportLimit` enable bit. Enabling/disabling the master switch must currently be done via the Growatt ShineServer web portal or ShinePhone app. Setting a non-zero rate via the bridge while the master switch is `0` will have no visible effect until the switch is enabled.

---

## Dependencies

- **Physical Growatt TPM meter installed:** Non-negotiable. RS485-connected, correctly wired to inverter.
- **RS485 communication confirmed:** Before writing this parameter, verify that the meter is detected by the inverter. Check Growatt ShinePhone app → Device Settings → Export Limit to confirm meter status shows "Connected".
- **`meter_acknowledged=true`:** The bridge will refuse the write without this field set to `true`.
- **`exportLimit` master switch:** Currently must be enabled via Growatt ShineServer web interface. The bridge does not expose a separate toggle for this master bit.
- **3-phase vs single-phase consistency:** Ensure `backFlowSingleCtrl` matches local grid operator requirements before enabling. For Poland: `0` (total system level).

---

## Risk level

**High.**

- **Without a meter:** Enabling this feature causes immediate inverter faults (F04/communication error on many firmware versions). The inverter may enter a fault state that requires manual reset.
- **With a meter, wrong phase mode:** Setting `backFlowSingleCtrl=1` in a jurisdiction that uses total-system metering causes incorrect throttling — the inverter may curtail generation unnecessarily (economic loss) or fail to curtail enough on an individual phase (grid compliance violation).
- **With a meter, correct setup:** Risk is low. A misconfigured percentage wastes PV generation (if set too low) or violates grid operator agreements (if set too high), but does not damage hardware.

The `meter_acknowledged` safety gate in the bridge is specifically designed to prevent the most common dangerous misconfiguration: enabling this parameter without verifying physical hardware is in place.

---

## Example

**Scenario:** Grid operator agreement limits export to 5 kW on a 12 kW inverter. Growatt TPM is installed and communicating.

**Current state:**
```json
{"export_limit_enabled": false, "export_limit_power_rate": 0}
```

**Step 1 — Enable master switch via ShineServer portal** (outside bridge scope)

**Step 2 — Set export limit to ~42% (5,000 W / 12,000 W ≈ 41.7%, round up to 42):**

```http
POST /api/v1/devices/TSS1F5M04Y/commands/set_export_limit
{
  "params": {
    "value": 42,
    "meter_acknowledged": true
  }
}
```

**After:**
```json
{"export_limit_enabled": true, "export_limit_power_rate": 42}
```

**Effective cap:** 42% of 12,000 W = 5,040 W. Grid receives at most ~5 kW during peak PV generation.

**Validate first (no hardware change):**

```http
POST /api/v1/devices/TSS1F5M04Y/commands/set_export_limit/validate
{
  "params": {
    "value": 42,
    "meter_acknowledged": true
  }
}
```

---

## Meter failure scenario

If the TPM loses RS485 communication while export limiting is active with `backflowDefaultPower=0`:

1. Inverter detects meter loss
2. Inverter reduces AC output to 0 W (or minimum controllable level)
3. Local loads are covered by grid import
4. Alarm/fault logged to Growatt cloud
5. When RS485 is restored, inverter resumes normal export-limited operation

This is the safest possible failure mode for grid compliance. For self-consumption, it is the worst case (all load on grid during meter fault). Weigh accordingly.

---

## See also

- [safety-constraints.md](safety-constraints.md) — grid protection parameters that must not be modified
- [battery-policy.md](battery-policy.md) — SOC and AC charge settings that interact with zero-export scenarios
- External: [Growatt Export Limitation Guide (growatt.pl)](https://growatt.pl/wp-content/uploads/2020/01/Growatt-Export-Limitation-Guide.pdf)
- External: [TLX Export Limit Guide (raystech.com.au)](https://www.raystech.com.au/wp-content/uploads/TLX-Export-limit.pdf)
