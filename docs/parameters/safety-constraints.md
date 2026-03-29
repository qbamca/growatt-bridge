# Safety Constraints — What Not to Change and Why

**Applies to:** Growatt MOD 12KTL3-HU + APX5 P2 battery (MIN/TLX family, device type 7)

---

## Overview

The bridge exposes a deliberately small set of named write operations. This document explains what is **intentionally excluded** from the bridge's write surface and why these parameters must not be modified via the API — or at all, in most cases.

The threat model is: **the LLM agent hallucinates a parameter name or value, or reasons incorrectly about inverter state.** Every parameter listed here, if written with a wrong value, can cause one or more of:

- Inverter disconnecting from the grid (causing power outage for local loads)
- Grid code compliance violation (regulatory/legal consequences)
- Battery hardware damage (accelerated degradation or BMS protection trigger)
- Uncontrolled export in excess of grid operator agreement
- Permanent firmware corruption (in the worst cases)

The bridge's defence is architectural: **if a parameter_id is not in `OPERATION_REGISTRY` in `safety.py`, it cannot be written.** There is no passthrough endpoint.

---

## Category 1 — Grid protection parameters

These parameters define the inverter's safety disconnect thresholds for grid voltage, frequency, and ride-through behaviour. They are set by the installer to comply with the **national grid code** (Poland: EN 50549-1/-2 and local DSO requirements, mapped to `gridCode=8968` on `TSS1F5M04Y`).

**Never modify:**

| Raw parameter | Description | Why dangerous |
|--------------|-------------|---------------|
| `gridCode` | Selected national grid standard (8968 = Poland EN 50549) | Changing this reprograms all grid protection thresholds to a different country's standards. Wrong settings → inverter may not disconnect during actual grid faults, violating the connection agreement and endangering utility workers. |
| `frequencyHighLimit` / `frequencyLowLimit` | Grid frequency operating window (50.05 / 49.0 Hz) | Widening the window delays disconnection during frequency excursions — grid code violation. Narrowing causes nuisance tripping under normal grid fluctuations. |
| `voltageHighLimit` / `voltageLowLimit` | Grid voltage operating window (440 / 340 V) | Same as above for voltage. Wrong limits → non-compliant disconnection timing. |
| `overVolt1`–`overVolt3` / `underVolt1`–`underVolt3` | Overvoltage/undervoltage trip thresholds | Disconnection levels — cannot exceed code-mandated values. Misconfiguration causes non-compliance with EN 50549 grid codes. |
| `overFreq1`–`overFreq3` / `underFreq1`–`underFreq3` | Over/underfrequency trip thresholds | Same as above for frequency. |
| `overVoltTime1`–`overVoltTime3` etc. | Response time limits for protection levels | Grid codes mandate maximum response times. Relaxing them (longer times) means the inverter stays connected during fault conditions longer than permitted. |
| `uwHVRTEE` / `uwHVRT2EE` | High Voltage Ride-Through thresholds | HVRT defines when the inverter stays connected vs trips during voltage sags/swells — required by grid codes for distributed generation above a certain capacity. |
| `uwLVRTEE` / `uwLVRT2EE` | Low Voltage Ride-Through thresholds | Same for undervoltage events. |
| `antiIslandEnable` | Anti-islanding protection | Must remain active. Anti-islanding prevents the inverter from energising a dead grid section, which is a lethal hazard for utility workers. Disabling it is illegal in all EU jurisdictions. |
| `safetyNum` / `safetyCorrespondNum` | Safety standard index codes | These map to preset protection profiles. Changing them without understanding the full protection table reprograms the entire protection scheme unpredictably. |

**How to correctly change them:** Contact the original installer or a qualified electrician. Use the Growatt ShineServer professional portal (requires installer-level credentials). Changes may require documentation submission to the local DSO.

---

## Category 2 — Reactive power and power factor control

The Q(V) reactive power curve and power factor settings are set by the grid operator or installer as part of the grid connection agreement. They define how the inverter supports grid voltage.

**Never modify via API:**

| Raw parameter | Description | Why dangerous |
|--------------|-------------|---------------|
| `qvH1` / `qvH2` / `qvL1` / `qvL2` | Q(V) voltage breakpoints (424, 432, 376, 368 V) | These define at what voltages the inverter injects or absorbs reactive power. Changing them alters the inverter's grid voltage support behaviour — required to match the DSO-specified Q(V) profile for the installation. |
| `qPercentMax` / `qvInLVPowerPer` / `qvOutHVPowerPer` | Maximum reactive power percentage | Caps reactive power contribution. Exceeding the agreed limit can overload distribution transformers. |
| `reactiveOutputEnable` / `reactiveRate` | Reactive power control master switch and rate | Activating or changing these without DSO coordination may violate grid connection terms. |
| `pfModel` / `pflinep1_pf`–`pflinep4_pf` | Power factor curve model | Power factor requirements are grid-operator-mandated. Changing these is a connection agreement violation. |
| `activePowerEnable` / `activeRate` | Active power control (P(f) droop) | Frequency-watt response settings. Changing them affects the inverter's contribution to grid frequency regulation. Misconfiguration can destabilise local grid during frequency events. |
| `puEnable` | Per-unit power control | Part of the reactive power regulation scheme. |

---

## Category 3 — Operating mode and system architecture

These parameters define the fundamental operation mode of the inverter and battery system. They interact with TOU scheduling and battery policy in non-obvious ways.

**Do not modify via API without full understanding:**

| Raw parameter | Description | Why dangerous |
|--------------|-------------|---------------|
| `onOff` | Inverter on/off switch (currently `1`) | Setting to `0` shuts down the inverter. All local loads transfer to grid (or fail if grid is unavailable). Recovery requires manual intervention or re-sending the API command. Not exposed in bridge by design. |
| `uwSysWorkMode` | System work mode (0=load first) | This is the global fallback mode when no TOU segment is active. The bridge controls TOU segments instead. Changing `uwSysWorkMode` directly bypasses TOU logic and may produce unexpected interactions with enabled segments. |
| `onGridMode` | On-grid mode variant | Changes fundamental inverter operating philosophy. Firmware-specific; wrong value may cause inverter to exit normal grid-tied operation. |
| `bsystemWorkMode` | Battery system work mode | Controls battery-level operating strategy independently of inverter mode. Interaction with TOU segments is documented only partially in Growatt API guide. |
| `bgridType` | Grid type (1=3-phase) | Must match physical wiring. Setting to `0` (single-phase) on a 3-phase installation disables two phases of output. Hardware damage is possible. |
| `epsFunEn` / `epsFreqSet` / `epsVoltSet` | EPS (Emergency Power Supply) function | EPS is the off-grid backup mode. Enabling it reconfigures the inverter's output switching logic. Incorrect frequency/voltage setpoints can damage loads connected during a power outage. Not exposed in bridge. |
| `genCtrl` / `genRatedPower` / `genChargeEnable` | Generator control settings | Currently `0` — no generator connected. Writing non-zero values enables generator management mode, which fundamentally changes charging logic. Do not touch without a generator physically installed. |
| `rrcrEnable` | RRCR (Ripple Control Relay Receiver) enable | Grid operator frequency-control integration. Enabling or disabling affects participation in grid balancing schemes. Country/DSO-specific. |

---

## Category 4 — Battery hardware limits and BMS integration

The battery hardware limits are set during commissioning to match the specific battery chemistry, cell count, and BMS firmware. They are not operating parameters — they are safety limits that match the physical hardware.

**Never modify:**

| Raw parameter | Description | Why dangerous |
|--------------|-------------|---------------|
| `batSysEnergy` | Battery system total energy capacity (50 kWh for APX5 P2) | Informational field used for SOC calculation. Changing it corrupts SOC readings, which then cascade into incorrect discharge stop behaviour. |
| `batteryType` | Battery chemistry/type code (202) | Must match the connected battery module. Wrong code → BMS communication protocol mismatch → battery management failure. |
| `batTempUpperLimitC` / `batTempUpperLimitD` | Battery temperature upper safety limits | Hardware-specific thermal protection thresholds set by the battery manufacturer. Raising them risks thermal runaway. |
| `batTempLowerLimitC` / `batTempLowerLimitD` | Battery temperature lower safety limits | Charging lithium cells below 0°C causes lithium plating, which is a fire risk. These limits prevent cold charging. Do not lower them. |
| `batSeriesNum` / `batParallelNum` | Battery module count (series/parallel) | Must match physical configuration. Wrong values corrupt voltage and current calculations used by the BDC. |
| `floatChargeCurrentLimit` | Float charge current limit | Terminal charge phase current cap. Set to `0` (auto) by default. Non-zero values may be incompatible with APX5 P2 BMS specification. |
| `vbatStartForDischarge` / `vbatStopForDischarge` | Voltage-based discharge thresholds | Currently `0` (SOC-based control). Switching to voltage-based control requires exact knowledge of the APX5 P2 cell voltage curves. Wrong values cause premature or over-discharge. |
| `vbatStartforCharge` / `vbatStopForCharge` | Voltage-based charge thresholds | Same as above for charging. |
| `vbatWarning` / `vbatWarnClr` | Low battery voltage warning thresholds | Alarm calibration. Changing may suppress warnings before actual hardware limits are reached. |

---

## Category 5 — Parameters that are currently no-ops but must remain so

Some parameters are `0` or disabled because the corresponding hardware or feature is not installed or not applicable to this installation. Setting them to non-zero values on this inverter would have undefined behaviour.

| Raw parameter | Current value | Why it must remain zero/disabled |
|--------------|---------------|----------------------------------|
| `dryContactFuncEn` | `0` | No dry contact relay wired. Enabling activates relay switching logic with no physical output — unpredictable firmware behaviour. |
| `synEnable` | `0` | No generator — generator synchronisation must remain disabled. |
| `demandManageEnable` | `0` | Demand management requires compatible load controllers. Not installed. |
| `peakShavingEnable` | `0` | Peak shaving requires additional cloud configuration and load monitoring. Not configured. |
| `maintainModeRequest` | `0` | Maintenance mode disables normal operation. Can only be activated intentionally with clear intent to resume afterwards. |
| `afciEnabled` | `0` | AFCI (Arc Fault Circuit Interrupter) requires compatible PV wiring. Enabling without appropriate hardware may cause false-positive arc detection and nuisance shutdowns. |
| `powerDownEnable` | `0` | Automatic power-down. Enabling without knowing the trigger conditions may cause unexpected shutdowns. |
| `enableNLine` | `0` | Neutral line output — hardware-specific; incorrect setting damages the inverter output stage. |

---

## What the bridge protects against

The bridge's `OPERATION_REGISTRY` in `safety.py` is the enforcement mechanism. It is exhaustive by design: anything not in the registry cannot be written.

**The most dangerous failure mode the bridge prevents:**

The Growatt `min_write_parameter` API accepts an arbitrary `parameter_id` string with no validation. An agent that constructs raw API calls could write any of the parameters above with any value. The bridge's architecture ensures this is impossible — there is no `/commands/raw_parameter` endpoint and none will ever be added.

**What the bridge allows (complete list as of current implementation):**

1. `set_ac_charge_stop_soc` — AC (grid) charge stops at this SOC (10–100%). **The only operation registered until others are integration-tested.**

**Everything else requires manual intervention via Growatt ShineServer (professional portal) or ShinePhone app.** Additional named operations can be re-added in `OPERATION_REGISTRY` only after end-to-end validation.

---

## Before calling any write operation

1. **Validate first:** Use the `/validate` endpoint to check parameters without touching hardware.
2. **Read current state:** Call `GET /api/v1/devices/{sn}/config` before writing. Confirm the current value and understand what will change.
3. **Check the audit log:** Recent writes appear in the JSONL audit log (`BRIDGE_AUDIT_LOG`). If another operation ran recently, understand its effect before stacking another write.
4. **Respect the rate limit:** The bridge enforces a maximum of `BRIDGE_RATE_LIMIT_WRITES` writes per minute (default: 3). Rapid writes are a sign that something is wrong with the control logic.
5. **Verify readback:** After a write, check the `readback` field in the response. If `readback_failed` is `true`, follow up with `GET /api/v1/devices/{sn}/config` to confirm the change landed.

---

## See also

- [time-segments.md](time-segments.md) — safe TOU schedule configuration
- [charge-discharge.md](charge-discharge.md) — safe power rate adjustments
- [battery-policy.md](battery-policy.md) — safe SOC boundary configuration
- [export-limit.md](export-limit.md) — export limiting with hardware requirements
- [`src/growatt_bridge/safety.py`](../../src/growatt_bridge/safety.py) — bridge enforcement implementation
- [`docs/security.md`](../security.md) — full threat model and risk mitigations
