"""Human-readable labels for Shine ``readAllMinParam`` / TLX setting bean keys.

Primary naming reference: **TLX device settings UI** (English strings in Shine
``setTLX`` / OSS), merged with technical meaning where useful. See also
``docs/parameter-glossary.md`` §4. Used by ``map_read_all_min_param.py`` only;
not imported by the bridge runtime.
"""

from __future__ import annotations

import re
from typing import Literal

Group = Literal[
    "identity",
    "schedule",
    "battery",
    "grid_export",
    "grid_protection",
    "reactive_pf",
    "operating_mode",
    "afci",
    "misc",
]

# Exact overrides where pattern matching is wrong or insufficient
_OVERRIDES: dict[str, tuple[str, Group]] = {
    # Identity / meta
    "sn": ("Inverter serial number", "identity"),
    "plantId": ("Growatt plant ID", "identity"),
    "datalogSn": ("ShineWiFi / datalogger serial", "identity"),
    "address": ("Modbus / comm address", "identity"),
    "deviceType": ("Portal device type code (differs from device_list type)", "identity"),
    "model": ("Internal numeric model ID (opaque)", "identity"),
    "modelText": ("Encoded model string (hardware variant)", "identity"),
    "deviceModel": ("Human-readable model name (e.g. MOD 12KTL3-HU)", "identity"),
    "nominalPower": ("Rated AC power (W)", "identity"),
    "activePower": ("Active power limit or capability (W)", "identity"),
    "innerVersion": ("Inverter internal firmware version", "identity"),
    "fwVersion": ("Main firmware version string", "identity"),
    "communicationVersion": ("Comms / BDC protocol version (e.g. ZBDC-xxxx)", "identity"),
    "modbusVersion": ("Modbus map / protocol revision", "identity"),
    "hwVersion": ("Hardware version (often unset)", "identity"),
    "m3VersionFlag": ("M3 platform / PCB revision flag", "identity"),
    "safetyVersion": ("Safety firmware / grid-code package version", "identity"),
    "lastUpdateTime": ("Last settings snapshot time (plant local)", "identity"),
    "sysTime": ("Inverter system time string", "identity"),
    "timezone": ("Timezone index / offset code", "identity"),
    "plantCountry": ("Plant country (display)", "identity"),
    "countryAndArea": ("Country / region (display)", "identity"),
    "location": ("User location string", "identity"),
    "alias": ("User device alias", "identity"),
    "lost": ("Communication lost flag (string bool)", "identity"),
    "status": ("Device status code", "identity"),
    "onGridStatus": ("On-grid connection status", "identity"),
    "ptoStatus": ("Permission-to-operate / grid permission status", "identity"),
    "onOff": ("Inverter run enable (1=on)", "operating_mode"),
    "dtc": ("Device type / product code (numeric)", "identity"),
    "eMonth": ("Monthly energy / CO2 display value (Growatt internal units)", "misc"),
    "bdcStatus": ("Battery DC converter status", "battery"),
    "bdcMode": ("BDC operating mode code", "battery"),
    "haveBdc": ("BDC module present", "battery"),
    "haveAfci": ("AFCI hardware present", "afci"),
    "isWinterDevice": ("Winter-mode capable hardware", "operating_mode"),
    "usBatteryType": ("Battery chemistry / region type code", "battery"),
    "sysMtncAvail": ("System maintenance menu available", "misc"),
    "lcdLanguage": ("LCD Language — HMI panel language (enum)", "operating_mode"),
    "maxAllowCurr": (
        "Maximum allowed current at busbar — protection profile limit (A)",
        "grid_protection",
    ),
    "failSafeCurr": (
        "Fail Safe Current — fallback current below max busbar (A); must be < max allowed",
        "grid_protection",
    ),
    "pf": ("PF or reactive setpoint — value depends on PF mode (cos φ, %, or var)", "reactive_pf"),
    "pfModel": (
        "Set Reactive Power mode — PF Fixed / Set PF / Q(V) / fixed Q / … (enum)",
        "reactive_pf",
    ),
    "yearSettingFlag": ("Year-based schedule enabled", "schedule"),
    "yearMonthTime": ("Year/month schedule override (encoded or null)", "schedule"),
    "showPeakShaving": ("Show peak shaving in UI", "operating_mode"),
    "compatibleFlag": ("Firmware compatibility flag", "misc"),
    "protEnable": ("Protection Enable — busbar / switchboard protection profile", "grid_protection"),
    "vActiveCutoffPowerPer": (
        "Voltage Active Cut-Off Power Percentage — PU-related active power cap (%)",
        "reactive_pf",
    ),
    "pvPfCmdMemoryState": ("PV power-factor command memory / hold state", "reactive_pf"),
    "fftThresholdCount": (
        "Max Accumulated Counts for Over FFT Value — AFCI FFT arc bucket (0–255)",
        "afci",
    ),
    "prePto": (
        "Pre PTO — pre-permission export/no-feed mode until cancelled (one-shot)",
        "operating_mode",
    ),
    "synEnable": ("SYN communication Enable — external sync / generator interface", "operating_mode"),
    # ub* = upper-bound style limits in Shine (stop SoC, backup reserve)
    "ubAcChargingStopSOC": (
        "Charge Stop SOC from Grid — stop grid charging at this SoC (%)",
        "battery",
    ),
    "ubPeakShavingBackupSOC": (
        "Reserved SOC for Peak Shaving — minimum battery SoC kept for peak shaving (%)",
        "battery",
    ),
}


def describe_key(key: str) -> tuple[str, Group]:
    """Return (human-readable label, category) for a raw API key."""
    if key in _OVERRIDES:
        return _OVERRIDES[key]

    # TOU / schedule (yearly)
    m = re.fullmatch(r"yearTime(\d)", key)
    if m:
        return (f"Year TOU slot {m.group(1)} (mode_startH_startM_stopH_stopM_flags)", "schedule")
    m = re.fullmatch(r"time(\d)Mode", key)
    if m:
        return (f"TOU slot {m.group(1)} battery/grid/load mode", "schedule")
    m = re.fullmatch(r"forcedTimeStart(\d)", key)
    if m:
        return (f"Forced window {m.group(1)} start (HH:MM)", "schedule")
    m = re.fullmatch(r"forcedTimeStop(\d)", key)
    if m:
        return (f"Forced window {m.group(1)} end (HH:MM)", "schedule")
    m = re.fullmatch(r"forcedStopSwitch(\d)", key)
    if m:
        return (f"Forced window {m.group(1)} enable (0/1)", "schedule")

    m = re.fullmatch(r"season(\d)Time(\d)", key)
    if m:
        return (f"Season {m.group(1)} TOU slot {m.group(2)} (encoded)", "schedule")
    m = re.fullmatch(r"season(\d)MonthTime", key)
    if m:
        return (f"Season {m.group(1)} active months (encoded)", "schedule")

    m = re.fullmatch(r"special(\d)Time(\d)", key)
    if m:
        return (f"Special period {m.group(1)} TOU slot {m.group(2)} (encoded)", "schedule")
    m = re.fullmatch(r"special(\d)MonthTime", key)
    if m:
        return (f"Special period {m.group(1)} month range (encoded)", "schedule")

    # Grid ride-through / limits (uw* = Growatt internal prefix; EE = parameter set).
    # Labels align with TLX “Regulation parameter setting” table; technical role in parentheses.
    rt_map = {
        "uwHVRTEE": "AC Voltage High 1 — high-voltage ride-through level 1 (V)",
        "uwHVRT2EE": "AC Voltage High 2 — HVRT level 2 (V)",
        "uwLVRTEE": "AC Voltage Low 1 — low-voltage ride-through level 1 (V)",
        "uwLVRT2EE": "AC Voltage Low 2 — LVRT level 2 (V)",
        "uwHFRTEE": "AC Frequency High 1 — high-frequency ride-through level 1 (Hz)",
        "uwHFRT2EE": "AC Frequency High 2 — HFRT level 2 (Hz)",
        "uwLFRTEE": "AC Frequency Low 1 — low-frequency ride-through level 1 (Hz)",
        "uwLFRT2EE": "AC Frequency Low 2 — LFRT level 2 (Hz)",
        "uwAcChargingMaxPowerLimit": "Max. Charge Power From Grid — AC charging power cap when grid charging is on (kW)",
        "uwDemandMgtRevsePowerLimit": "Export Limit — peak shaving / demand management export cap (kW)",
        "uwDemandMgtDownStrmPowerLimit": "Import Limit — peak shaving / demand management import cap (kW)",
    }
    if key in rt_map:
        return (rt_map[key], "grid_protection")

    # Reactive Q(V) / PF curve (TLX “Q(V) setting”)
    qv = {
        "qvH1": "Q (V) cut into high Voltage — upper knee on Q(V) curve (V)",
        "qvH2": "Q (V) cut out high Voltage — high-voltage exit knee (V)",
        "qvL1": "Q (V) cut into low Voltage — lower knee on Q(V) curve (V)",
        "qvL2": "Q (V) cut out low Voltage — low-voltage exit knee (V)",
        "qvInLVPowerPer": "Q(V) Cut Into Low Voltage Power Percentage (%)",
        "qvOutHVPowerPer": "Q(V) Cut Out High Voltage Power Percentage (%)",
        "qPercentMax": "Q (V) reactive power percentage — max reactive vs rated (%)",
    }
    if key in qv:
        return (qv[key], "reactive_pf")

    m = re.fullmatch(r"pflinep(\d)_(lp|pf)", key)
    if m:
        kind = "active power %" if m.group(2) == "lp" else "power factor"
        return (f"PF curve breakpoint {m.group(1)} — {kind}", "reactive_pf")

    # Battery SoC / voltage (TLX “Battery Settings”; Shine bean field names)
    bat = {
        "chargePowerCommand": "Charging Power Rate — max charge power (% of rated)",
        "disChargePowerCommand": "Discharging Power Rate — max discharge power (% of rated)",
        "onGridDischargeStopSOC": "On-grid Battery Discharge Stop SOC — floor while grid-tied (%)",
        "acChargeEnable": "Grid Charging — allow energy from grid to charge battery (enable)",
        "wchargeSOCLowLimit": "Charge Stop SOC — stop charging when SoC reaches this (%)",
        "wdisChargeSOCLowLimit": "Discharging Stop SOC — stop discharging when SoC reaches this (%)",
        "vbatStartforCharge": "Battery voltage threshold to start charging (V; 0 = use SoC mode)",
        "vbatStartForDischarge": "Battery voltage threshold to start discharging (V)",
        "vbatStopForCharge": "Stop charging at this battery voltage (V)",
        "vbatStopForDischarge": "Stop discharging at this battery voltage (V)",
        "vbatWarning": "Battery low-voltage warning threshold (V)",
        "vbatWarnClr": "Battery warning clear voltage (V)",
        "floatChargeCurrentLimit": "Float charge current limit (A)",
    }
    if key in bat:
        return (bat[key], "battery")

    # Grid export (TLX “Export limit setting” / anti-backflow)
    ex = {
        "exportLimit": "Set Exportlimit — anti-backflow mode (disable / meter / CT per UI)",
        "exportLimitPowerRate": "Export limit value — % of rated or absolute power (per meter mode)",
        "backFlowSingleCtrl": "Phase level — per-phase vs total export limiting",
        "backflowDefaultPower": "Default Power After Exportlimit Failure — fallback when meter/CT fails (% or W per model)",
    }
    if key in ex:
        return (ex[key], "grid_export")

    # Voltage / frequency window and trip times (TLX “Grid parameters” + regulation tables)
    gp = {
        "voltageHighLimit": "Overvoltage Limit — user grid-tied overvoltage window (V)",
        "voltageLowLimit": "Undervoltage Limit — user grid-tied undervoltage window (V)",
        "frequencyHighLimit": "Over Frequency Limit — user overfrequency window (Hz)",
        "frequencyLowLimit": "Under Frequency Limit — user underfrequency window (Hz)",
        "overVolt3": "Third order overpressure point — protection tier 3 (V)",
        "underVolt3": "Third order undervoltage point — protection tier 3 (V)",
        "overVoltTime1": "Overvoltage Time U> — trip delay tier 1 (ms)",
        "overVoltTime2": "Overvoltage Time U>> — trip delay tier 2 (ms)",
        "overVoltTime3": "Third order overpressure time point (ms)",
        "underVoltTime1": "Undervoltage Time U< — trip delay tier 1 (ms)",
        "underVoltTime2": "Undervoltage Time U<< — trip delay tier 2 (ms)",
        "underVoltTime3": "Third order undervoltage time point (ms)",
        "overFreq3": "Third-order overtone / overfrequency protection point (Hz)",
        "underFreq3": "Third-order underfrequency point (Hz)",
        "overFreqTime1": "Overfrequency Time f> — trip delay tier 1 (ms)",
        "overFreqTime2": "Overfrequency Time f>> — trip delay tier 2 (ms)",
        "overFreqTime3": "Third-order overclocking time point (ms)",
        "underFreqTime1": "Underfrequency Time f< — trip delay tier 1 (ms)",
        "underFreqTime2": "Underfrequency Time f<< — trip delay tier 2 (ms)",
        "underFreqTime3": "Third order underfrequency time point (ms)",
        "overFreDropPoint": "Over Frequency Derating Start Point — freq-watt droop start (Hz)",
        "overFreLoRedSlope": "Over Frequency Derating Rate — power reduction vs frequency",
        "overFreLoRedDelayTime": "Over Frequency Derating Start Delay Time (ms; step rules vary by DTC)",
        "gridHVReduceLoadLow": "Low Voltage Load Drop Point Of The Grid (PU / HV reduction, V)",
        "gridHVReduceLoadHigh": "High Voltage Load Drop Point Of The Grid (PU / HV reduction, V)",
        "antiIslandEnable": "Active anti-islanding — enable/disable (enum; 0=enable in TLX select)",
    }
    if key in gp:
        return (gp[key], "grid_protection")

    safety = {
        "safetyNum": "Safety Standard / grid-code profile code (region)",
        "safetyCorrespondNum": "Country / Region — safety sub-profile index (matches grid-code list)",
    }
    if key in safety:
        return (safety[key], "grid_protection")

    # Reactive / active power control (TLX Command rows)
    rp = {
        "reactiveOutputEnable": "Reactive output mode — whether reactive power var limit applies",
        "reactiveRate": "Reactive power setpoint — % or var depending on PF mode",
        "activePowerEnable": "Active power limitation enabled (when exposed)",
        "activeRate": "Set Active Power — limit as % of rated or absolute power (W); mode from UI",
        "puEnable": "P(U) Enable — voltage-active power droop (when PU module shown)",
    }
    if key in rp:
        return (rp[key], "reactive_pf")

    # Operating mode / features
    om = {
        "onGridMode": "Grid-connection settings — automatic vs manual on-grid",
        "bsystemWorkMode": "Work Mode — default / retrofit / multi-parallel (Dual CT mode label on some DTCs)",
        "bgridType": "Grid Type — single / three / split phase",
        "rrcrEnable": "RRCR Enable — ripple / DRM receiver (with PU on some models)",
        "demandManageEnable": "Peak Shaving Mode enable — pairs with import/export limits",
        "peakShavingEnable": "Reserved SOC for Peak Shaving enable",
        "winModeFlag": "Winter mode schedule active (OSS winter module)",
        "winModeStartTime": "Winter mode period start (date)",
        "winModeEndTime": "Winter mode period end (date)",
        "winModeOnGridDischargeStopSOC": "Winter mode On-grid discharge stop SOC (%)",
        "winModeOffGridDischargeStopSOC": "Winter mode Off-grid discharge stop SOC (%)",
        "maintainModeRequest": "Maintenance mode requested",
        "maintainModeStartTime": "Maintenance window start",
        "epsFunEn": "Set Backup On/Off — EPS / backup output enable",
        "epsFreqSet": "Set Backup Frequency — EPS output Hz",
        "epsVoltSet": "Set Backup Voltage — EPS output V (enum)",
        "sleepOffGridEnable": "Off-grid in battery sleep mode Enable/Disable",
        "powerDownEnable": "LG Battery Power-saving Enable",
        "genCtrl": "Generator Control — force on / off / not forced",
        "genRatedPower": "Generator Rating (W)",
        "genChargeEnable": "Generator Charge Enable",
        "dryContactFuncEn": "Dry Contact Function enable",
        "dryContactOnRate": "Dry Contact Opening Power Rate (%)",
        "dryContactOffRate": "Dry Contact Closing Power Rate (%)",
        "dryContactPower": "Dry contact power / rate (context-specific %)",
        "exterCommOffGridEn": "Manual Offgrid Enable (when row shown)",
        "limitDevice": "Dynamometer — meter vs CT for limiter",
        "enableNLine": "Neutral line Disable — N-conductor control (inverted sense in UI)",
        "loadingRate": "Loading rate — startup ramp (%Pn)",
        "restartLoadingRate": "Restart loading rate — reconnect ramp (%Pn)",
        # Primary TLX use: Q(V) delay; same key may appear in other modbus contexts.
        "delayTime": "Q (V) delay time — reactive response delay (ms; seconds on some DTCs in UI)",
    }
    if key in om:
        return (om[key], "operating_mode")

    afci = {
        "afciEnabled": "AFCIEnable — arc-fault detection on/off",
        "afciSelfCheck": "AFCIChecking — periodic self-test",
        "afciReset": "AFCIReset — reset latch / clear",
        "afciThresholdH": "AFCIThreshold(High) — high arc-sense threshold",
        "afciThresholdL": "AFCIThreshold(Low) — low arc-sense threshold",
        "afciThresholdD": "AFCIThreshold(In) — mid / in-band threshold",
    }
    if key in afci:
        return (afci[key], "afci")

    # Fallback: spaced camelCase
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    spaced = re.sub(r"(\d)", r" \1", spaced).strip()
    return (spaced[0].upper() + spaced[1:] if spaced else key, "misc")


def all_labels(keys: list[str]) -> list[tuple[str, str, Group]]:
    """Return sorted rows: (raw_key, label, group)."""
    out: list[tuple[str, str, Group]] = []
    for k in sorted(keys):
        label, group = describe_key(k)
        out.append((k, label, group))
    return out
