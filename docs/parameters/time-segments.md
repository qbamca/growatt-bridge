# Time-of-Use (TOU) Schedule — Time Segments

**Applies to:** Growatt MOD 12KTL3-HU + APX5 P2 battery (MIN/TLX family, device type 7)

---

## What it controls

The TOU schedule divides the 24-hour day into time windows, each with an assigned **operating mode** that tells the inverter how to prioritise between the solar array, battery, and grid. Up to **9 time slots** can be active simultaneously.

When the inverter's clock enters a segment's window, it shifts its power routing strategy:

- **Load-first (mode 0):** PV covers loads. Surplus charges the battery. Battery doesn't discharge to grid. Grid imports only when PV + battery are insufficient.
- **Battery-first (mode 1):** Battery discharges to cover loads ahead of the grid. PV still feeds loads directly. Useful for evening peak hours when import tariffs are high.
- **Grid-first (mode 2):** Battery charges from grid during the window (if AC charge is enabled). PV still feeds loads. Used during cheap off-peak tariff windows to pre-fill the battery.

Segments are evaluated in **slot order (1→9)**. If multiple segments overlap in time, lower-numbered slots take precedence (Growatt firmware behaviour — do not rely on this; configure non-overlapping windows).

Outside all defined/enabled segments the inverter falls back to its global `uwSysWorkMode` default (typically `0` = load-first).

---

## API mapping

| Action | growattServer method | Bridge operation ID |
|--------|---------------------|---------------------|
| Read all segments | `min_detail` → `tlxSetbean.forcedTimeStart1`…`forcedTimeStop9`, `time1Mode`…`time9Mode`, `forcedStopSwitch1`…`forcedStopSwitch9` | `GET /api/v1/devices/{sn}/config` or `GET /api/v1/devices/{sn}/config/time-segments` |
| Write one segment | `min_write_time_segment(device_sn, segment, mode, start_time, end_time, enabled)` | `POST /api/v1/devices/{sn}/commands/set_time_segment` |

The bridge calls `min_write_time_segment` with the exact parameters below. The underlying growattServer library translates these into the Growatt OpenAPI V1 `v1/tlxSet` call with the appropriate `yearTimeN` encoded string.

### Request body

```json
{
  "params": {
    "segment": 1,
    "mode": 1,
    "start_time": "06:00",
    "end_time": "22:00",
    "enabled": true
  }
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `segment` | integer | yes | Slot index 1–9 |
| `mode` | integer | yes | `0` load-first, `1` battery-first, `2` grid-first |
| `start_time` | string `HH:MM` | yes | Window open time (24h, e.g. `"06:30"`) |
| `end_time` | string `HH:MM` | yes | Window close time (24h, e.g. `"22:00"`) |
| `enabled` | boolean | no | Whether this slot is active (default `true`) |

---

## Valid ranges

| Parameter | Min | Max | Notes |
|-----------|-----|-----|-------|
| `segment` | 1 | 9 | MOD 12KTL3-HU firmware supports exactly 9 slots |
| `mode` | 0 | 2 | Only three modes defined in Growatt OpenAPI V1 |
| `start_time` | `00:00` | `23:59` | `HH:MM` 24-hour format |
| `end_time` | `00:00` | `23:59` | `HH:MM` 24-hour format |

**Boundary notes:**

- Setting `start_time == end_time` creates a zero-duration segment. The inverter may ignore it or treat it as always-active depending on firmware version. Avoid.
- `end_time` of `"23:59"` is the practical maximum for a night window. A window from `"22:00"` to `"06:00"` spanning midnight cannot be expressed in a single segment — use two segments: `"22:00"→"23:59"` and `"00:00"→"06:00"`.
- If `enabled=false`, the inverter ignores the segment's time window and mode; the slot record is preserved for later re-enabling.

---

## Default values (factory / post-reset)

After a factory reset, the MOD 12KTL3-HU ships with all 9 segments **disabled** (`forcedStopSwitch1-9 = 0`) and time fields set to `"0:0"`. The inverter operates in load-first mode continuously.

As observed on `TSS1F5M04Y` (2026-02-22):

| Segment | Mode | Start | End | Enabled |
|---------|------|-------|-----|---------|
| 1 | 2 (grid-first) | 13:30 | 15:00 | yes |
| 2 | 1 (battery-first) | 11:00 | 15:00 | yes |
| 3–9 | 0 | 00:00 | 00:00 | no |

These were user-configured; they do not represent Growatt factory defaults.

---

## Current value — how to read it

```
GET /api/v1/devices/{sn}/config/time-segments
```

Returns a list of `TimeSegment` objects (see `models.py`):

```json
[
  {"segment": 1, "mode": 2, "start_time": "13:30", "end_time": "15:00", "enabled": true},
  {"segment": 2, "mode": 1, "start_time": "11:00", "end_time": "15:00", "enabled": true},
  ...
]
```

Or from `GET /api/v1/devices/{sn}/config` in the `time_segments` array.

---

## Dependencies

- **Battery installed:** TOU scheduling only has observable effect if the APX5 P2 (or compatible battery) is connected and operational. Without a battery, modes `1` (battery-first) and `2` (grid-first charge) are no-ops.
- **AC charge enabled:** Grid-first mode (2) requires `acChargeEnable=1` (see [battery-policy.md](battery-policy.md)) to actually charge the battery from the grid. Without AC charge enabled, mode 2 acts like load-first.
- **`discharge_stop_soc`:** Battery-first discharge (mode 1) stops when `discharge_stop_soc` is reached. Ensure this is set sensibly (minimum 10%) before relying on battery-first windows. See [battery-policy.md](battery-policy.md).
- **Clock accuracy:** The inverter's internal clock must be synchronised. A drifted clock shifts all window boundaries. The Growatt datalogger (ShineWiFi-X) syncs the clock via NTP.

---

## Risk level

**Low** — This is the primary intended use case for the TOU API. A misconfigured segment causes suboptimal energy routing (e.g. discharging when you don't want to) but does not damage hardware or violate safety limits. The worst realistic outcome is importing more from the grid than expected, or failing to use cheap off-peak energy.

**Do not** create a permanent grid-first segment spanning all 24 hours — the battery will cycle on AC charging continuously, increasing wear. Limit grid-first windows to actual cheap tariff periods.

---

## Example

**Scenario:** Polish dynamic tariff — cheap grid energy from 22:00 to 06:00; peak consumption 07:00–21:00.

**Goal:** Pre-charge battery from grid overnight, discharge battery during peak hours.

**Configuration:**

```http
POST /api/v1/devices/TSS1F5M04Y/commands/set_time_segment
{
  "params": {"segment": 1, "mode": 2, "start_time": "22:00", "end_time": "23:59", "enabled": true}
}

POST /api/v1/devices/TSS1F5M04Y/commands/set_time_segment
{
  "params": {"segment": 2, "mode": 2, "start_time": "00:00", "end_time": "06:00", "enabled": true}
}

POST /api/v1/devices/TSS1F5M04Y/commands/set_time_segment
{
  "params": {"segment": 3, "mode": 1, "start_time": "07:00", "end_time": "21:59", "enabled": true}
}
```

**Result:**
- 22:00–06:00: battery charges from grid (grid-first) up to `ac_charge_stop_soc`
- 07:00–21:59: battery discharges to cover loads (battery-first) down to `discharge_stop_soc`
- Remaining hours (no enabled segment): load-first (PV covers loads, no forced charge/discharge)

**Validate before writing:**

```http
POST /api/v1/devices/TSS1F5M04Y/commands/set_time_segment/validate
{
  "params": {"segment": 1, "mode": 2, "start_time": "22:00", "end_time": "23:59", "enabled": true}
}
```

Returns `{"valid": true, "errors": []}` if parameters pass all safety checks without touching hardware.

---

## Readback behaviour

After a successful write, the bridge re-reads all time segments and returns the state of the written slot in the `readback` field of the response. If the readback slot's mode/times match what was sent, `unchanged` lists them. If the API returned different values (e.g. due to time rounding), `changed` shows the diff.

---

## See also

- [charge-discharge.md](charge-discharge.md) — power rate limits applied within TOU windows
- [battery-policy.md](battery-policy.md) — SOC floors and AC charge target for grid-first windows
- [safety-constraints.md](safety-constraints.md) — what not to change
