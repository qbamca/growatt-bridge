# Battery Policy — SOC Limits, AC Charge, and Winter Mode

**Applies to:** Growatt MOD 12KTL3-HU + APX5 P2 battery (MIN/TLX family, device type 7)

---

## What it controls

This document covers the four parameters that define the **battery operating envelope**: how low the battery can discharge, whether the grid can charge it, how much grid charging is allowed, and the winter-mode override. Together they determine the battery's effective usable range and grid interaction behaviour.

| Parameter | Operation ID | Controls |
|-----------|-------------|---------|
| Discharge stop SOC | `set_discharge_stop_soc` | Floor: battery won't discharge below this level |
| AC charge enable | `set_ac_charge_enable` | Whether grid → battery charging is permitted at all |
| AC charge stop SOC | `set_ac_charge_stop_soc` | Ceiling: grid charging stops at this SOC |

Winter mode parameters (`winModeFlag`, `winModeStartTime`, etc.) are **read-only** in the current bridge — they are not exposed as write operations because their interaction with the above parameters is complex and firmware-version-dependent. They are documented here for observability.

---

## 1. Discharge stop SOC (`set_discharge_stop_soc`)

### What it controls

Sets the **minimum state of charge (SOC)** below which the inverter will not discharge the APX5 P2 battery to supply loads or grid. When the battery SOC falls to this threshold, discharge is halted regardless of the active TOU mode or load demand. The inverter then draws from the grid to cover any remaining load.

This is a **software-enforced floor.** The APX5 P2 BMS also has its own hardware deep-discharge protection (typically at ~5–10% depending on cell chemistry), which operates independently of this setting. The bridge floor of **10%** is set above the BMS hardware floor to provide a comfortable margin.

### API mapping

| Item | Value |
|------|-------|
| Bridge operation ID | `set_discharge_stop_soc` |
| growattServer method | `min_write_parameter(device_sn, "discharge_stop_soc", value)` |
| Growatt parameter ID | `discharge_stop_soc` |
| API value type | Integer string (`"10"` – `"100"`) |
| Config read field | `discharge_stop_soc` in `NormalizedConfig` / `onGridDischargeStopSOC` in raw `tlxSetbean` |

**Request body:**

```json
{
  "params": {
    "value": 20
  }
}
```

### Valid range

| Min | Max | Notes |
|-----|-----|-------|
| **10** | 100 | The bridge hard-floors at 10% — values below 10 are rejected |

**Boundary notes:**

- **10%:** The bridge minimum. Leaves a small buffer above the APX5 P2 BMS hardware floor. Do not set below 10 — the bridge will reject it with a validation error. The original Growatt API accepts 0, but the bridge never passes 0 through.
- **100%:** Prevents all discharge. The battery is fully protected from discharging but is also completely unusable for load coverage. Only appropriate for intentional "battery reserve" configurations.
- **20%** (current device value): The practical recommended minimum for lithium iron phosphate (LFP) batteries to balance cycle life against usable capacity.
- **50%+:** Suitable when the battery serves primarily as emergency backup; ensures a meaningful reserve is always available for grid outage.

### Default values

As observed on `TSS1F5M04Y`:

| Raw field | Value | Meaning |
|-----------|-------|---------|
| `onGridDischargeStopSOC` | `20` | Battery discharges down to 20% before stopping |
| `wdisChargeSOCLowLimit` | `10` | Winter mode discharge stop SOC (separate, see winter mode below) |

### Risk level

**Medium.**

- Setting too low (10%): increased cell stress from deep discharge cycles, slightly shorter cycle life over years of use. No immediate hardware damage.
- Setting too high (e.g. 80%): wastes most of the battery's capacity; economic/efficiency loss, no safety risk.
- The bridge hard minimum of 10% prevents the physically dangerous case (SOC = 0%) where full discharge could trigger the BMS hardware protection, potentially requiring manual reset.

---

## 2. AC charge enable (`set_ac_charge_enable`)

### What it controls

Master switch for **grid-to-battery charging** (AC charge). When enabled (`true`), the inverter is allowed to pull power from the grid to charge the APX5 P2 battery. This is what makes TOU grid-first segments (mode 2) actually charge the battery — without AC charge enabled, grid-first segments only prevent battery discharge rather than actively charging from the grid.

When disabled (`false`), the battery can only be charged from PV. Grid power is used exclusively for loads.

### API mapping

| Item | Value |
|------|-------|
| Bridge operation ID | `set_ac_charge_enable` |
| growattServer method | `min_write_parameter(device_sn, "ac_charge", "1"/"0")` |
| Growatt parameter ID | `ac_charge` |
| API value type | `"1"` (enabled) or `"0"` (disabled) |
| Config read field | `ac_charge_enabled` in `NormalizedConfig` / `acChargeEnable` in raw `tlxSetbean` |

**Request body:**

```json
{
  "params": {
    "enabled": true
  }
}
```

### Valid values

| `enabled` | API value | Effect |
|-----------|-----------|--------|
| `true` | `"1"` | Grid → battery charging permitted (subject to `ac_charge_stop_soc` and TOU mode) |
| `false` | `"0"` | Grid → battery charging blocked; battery only charges from PV |

### Default values

As observed on `TSS1F5M04Y`:

| Raw field | Value | Meaning |
|-----------|-------|---------|
| `acChargeEnable` | `1` | AC charging currently **enabled** |

### Risk level

**Low.**

- `true`: Grid import increases during cheap-tariff windows (or whenever a grid-first TOU segment is active). Electricity cost may increase if tariff timing is misconfigured in the TOU schedule.
- `false`: Battery only charges from PV. Simpler behaviour, lower grid interaction. If PV is insufficient (e.g. winter, cloudy period), the battery may not charge fully.

No hardware risk in either direction.

---

## 3. AC charge stop SOC (`set_ac_charge_stop_soc`)

### What it controls

Sets the **maximum SOC at which grid-to-battery charging automatically stops**. When AC charge is enabled and the inverter is in a grid-first TOU segment, it will charge the battery from the grid until the SOC reaches this threshold, then stop. PV charging is not subject to this limit (PV charges to 100% or until battery is full).

This prevents the grid from topping off the battery beyond the desired ceiling — for example, keeping a 20% buffer free for PV absorption during the following day.

### API mapping

| Item | Value |
|------|-------|
| Bridge operation ID | `set_ac_charge_stop_soc` |
| growattServer method | `min_write_parameter(device_sn, "ac_charge_soc_limit", value)` |
| Growatt parameter ID | `ac_charge_soc_limit` |
| API value type | Integer string (`"10"` – `"100"`) |
| Config read field | `ac_charge_stop_soc` in `NormalizedConfig` / `ubAcChargingStopSOC` in raw `tlxSetbean` |

**Request body:**

```json
{
  "params": {
    "value": 80
  }
}
```

### Valid range

| Min | Max | Notes |
|-----|-----|-------|
| 10 | 100 | Bridge enforces minimum of 10% |

**Boundary notes:**

- **10%:** Setting AC charge stop SOC to 10% while AC charge is enabled effectively allows grid charging only between 10% and 10% — a zero-width window. In practice this disables AC charging without changing the enable flag.
- **80%** (current device value): Leaves 20% headroom for PV charging each morning. Recommended for systems with meaningful daily PV generation.
- **100%:** Grid charges battery to full. Maximises storage for overnight discharge but leaves no room for PV absorption at the start of the day (battery full → PV exports or is curtailed). Appropriate when PV is minimal or when the priority is backup capacity.

### Default values

As observed on `TSS1F5M04Y`:

| Raw field | Value | Meaning |
|-----------|-------|---------|
| `ubAcChargingStopSOC` | `80` | AC charging stops at 80% SOC |

### Risk level

**Low.**

- Setting too high (close to 100%): more grid import, less PV absorption capacity, higher electricity cost if PV is available the next morning.
- Setting too low: limits AC charge benefit; battery may not have enough stored energy for the evening discharge window.
- No hardware risk.

### Interaction with `discharge_stop_soc`

The AC charge stop SOC should be **above** the discharge stop SOC to give the battery a usable operating range. If `ac_charge_stop_soc == discharge_stop_soc`, the usable range is zero — the battery is always at the boundary and neither charges (already at ceiling) nor discharges (already at floor). This is not harmful but wastes the battery entirely.

Recommended: `ac_charge_stop_soc` ≥ `discharge_stop_soc` + 20%.

---

## Winter mode (read-only)

Winter mode is a Growatt feature that overrides the normal TOU/SOC settings during a configured calendar window. It is intended for climates with low winter PV yield, where the strategy should favour grid charging and deeper battery discharge to maximise self-sufficiency.

### Key winter mode fields (from `tlxSetbean`)

| Raw field | Value (TSS1F5M04Y) | Description |
|-----------|-------------------|-------------|
| `winModeFlag` | `0` | Winter mode inactive |
| `winModeStartTime` | `"null"` | Not configured |
| `winModeEndTime` | `"null"` | Not configured |
| `winModeOnGridDischargeStopSOC` | `0` | Override discharge stop SOC when on-grid in winter |
| `winModeOffGridDischargeStopSOC` | `0` | Override discharge stop SOC when off-grid in winter |
| `winOnGridSOC` / `winOffGridSOC` | `0` | Winter mode target SOC |
| `wdisChargeSOCLowLimit` | `10` | Winter mode discharge stop floor |
| `wchargeSOCLowLimit` | `100` | Winter mode max charge SOC |

### Why it is not exposed as a write operation

Winter mode interacts with the main SOC and TOU parameters in firmware-version-specific ways. On some MOD 12KTL3-HU firmware revisions, activating winter mode overrides `discharge_stop_soc` with `winModeOnGridDischargeStopSOC` in ways that are not fully documented in the OpenAPI V1 spec. Exposing it as a write without thorough per-firmware testing risks unexpected SOC behaviour. Configure winter mode through the Growatt ShinePhone app until the interaction is fully understood.

---

## Combined example — typical TOU + battery policy configuration

**Target:** Overnight cheap tariff, morning PV priority, evening battery discharge.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `discharge_stop_soc` | 20% | Keep 20% reserve; protect APX5 P2 cells |
| `ac_charge_enable` | `true` | Allow overnight grid charging |
| `ac_charge_stop_soc` | 80% | Leave 20% headroom for morning PV |
| TOU segment 1 | mode 2, 22:00–23:59 | Grid-first overnight (charge from grid) |
| TOU segment 2 | mode 2, 00:00–06:00 | Grid-first overnight continued |
| TOU segment 3 | mode 1, 07:00–21:59 | Battery-first during day/evening |

**Result:**
- 22:00–06:00: Battery charges from grid to 80% SOC
- 06:00–07:00: Load-first (PV covers loads, PV surplus charges battery above 80%)
- 07:00–21:59: Battery discharges to cover loads, stops at 20% SOC
- Battery usable range: 80% → 20% = 60% of 50 kWh (APX5 P2) = 30 kWh available for discharge

**Write sequence:**

```http
POST /api/v1/devices/TSS1F5M04Y/commands/set_discharge_stop_soc
{"params": {"value": 20}}

POST /api/v1/devices/TSS1F5M04Y/commands/set_ac_charge_enable
{"params": {"enabled": true}}

POST /api/v1/devices/TSS1F5M04Y/commands/set_ac_charge_stop_soc
{"params": {"value": 80}}
```

Then configure TOU segments per [time-segments.md](time-segments.md).

---

## See also

- [time-segments.md](time-segments.md) — TOU schedule that triggers grid-first and battery-first modes
- [charge-discharge.md](charge-discharge.md) — power rate limits applied during charge/discharge
- [safety-constraints.md](safety-constraints.md) — parameters that must not be changed via the bridge
