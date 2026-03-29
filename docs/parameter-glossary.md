# Growatt OpenAPI V1 Parameter Glossary

Field-level documentation for all known response properties from the Growatt OpenAPI V1, observed on device `TSS1F5M04Y` (Growatt MOD 12KTL3-HU — type 7 / MIN-TLX family with BDC battery module, 3-phase, 12kW AC, EU region).

Values captured on 2026-02-22 (daytime, inverter generating — solar active, battery at 20% SoC).

**Organization**: Properties are grouped by *domain* rather than API endpoint, to make it easier to understand what each field represents:

- **Section 1 — Plant & Site**: Properties describing a plant/site (from `plant_list`, `plant_details`)
- **Section 2 — Device Identity**: Properties describing what a device *is* (from `device_list`, `min_detail` top-level)
- **Section 3 — Telemetry**: Properties describing what a device is *doing* right now (from `min_energy`, `min_energy_history`)
- **Section 4 — Configuration**: Properties describing what a device is *set to* (from `min_detail.tlxSetbean`)

For each property: **description** + **[inference]** notes how its purpose was determined.

---

## Naming Conventions


| Prefix/suffix   | Meaning                                  | Basis                                                                       |
| --------------- | ---------------------------------------- | --------------------------------------------------------------------------- |
| `e` prefix      | Energy in kWh (cumulative or daily)      | Standard electrical notation; confirmed by kWh-scale values                 |
| `p` prefix      | Power in W or kW (instantaneous)         | Standard electrical notation; confirmed by W-scale values                   |
| `v` prefix      | Voltage in V                             | Standard electrical notation                                                |
| `i` prefix      | Current in A                             | Standard electrical notation                                                |
| `f` prefix      | Frequency in Hz                          | Standard electrical notation                                                |
| `Today` suffix  | Accumulated value since midnight         | Name + resets to small value each morning                                   |
| `Total` suffix  | Accumulated value since installation     | Name + large cumulative kWh values                                          |
| `bdc1` / `bdc2` | Battery DC Converter 1 / 2               | Growatt TLX-XH documentation: "BDC" is the battery power electronics module |
| `bms`           | Battery Management System                | Industry-standard acronym for battery monitoring/protection circuit         |
| `eps`           | Emergency Power Supply (off-grid output) | Growatt MIN-XH manual and API guide term for backup power output            |
| `vac`           | AC (grid) voltage                        | `v` + `ac`                                                                  |
| `vpv`           | PV string voltage                        | `v` + `pv`                                                                  |
| `ipv`           | PV string current                        | `i` + `pv`                                                                  |
| `ppv`           | PV string power                          | `p` + `pv`                                                                  |
| `pac`           | AC output power                          | `p` + `ac`                                                                  |


---

## 1. Plant & Site

Properties returned by `plant_list` and `plant_details`.

### 1.1 plant_list


| Property                    | Value              | Unit    | Description                                               | Inference                                                             |
| --------------------------- | ------------------ | ------- | --------------------------------------------------------- | --------------------------------------------------------------------- |
| `plant_id`                  | 10581915           | —       | Unique ID of the power plant/site                         | Name + used as key in subsequent API calls                            |
| `name`                      | "Dom"              | —       | User-defined plant name ("Dom" = "Home" in Polish)        | Name + string value                                                   |
| `country`                   | "Poland"           | —       | Country of the installation                               | Name + string value                                                   |
| `city`                      | "Mińsk Mazowiecki" | —       | City of the installation                                  | Name + string value                                                   |
| `latitude` / `longitude`    | 52.178 / 21.571    | degrees | GPS coordinates of the plant                              | Name + geographic coordinate range                                    |
| `latitude_f` / `latitude_d` | null               | —       | Alternate lat format (fractional/decimal) — not populated | Name analogy; null values suggest unused fields                       |
| `total_energy`              | "943.5"            | kWh     | Lifetime AC energy produced by the plant                  | Name + kWh-scale value consistent with system age and size            |
| `current_power`             | "382.3"            | W       | Current instantaneous output power of the plant           | Name + value matches daytime partial generation                       |
| `peak_power`                | 10.1               | kWp     | Installed DC peak capacity (sum of all PV panels)         | Name + kWp-scale; consistent with 12kW AC inverter with ~10kWp panels |
| `status`                    | 1                  | enum    | Plant status (1=normal/online, 0=offline)                 | Cross-referenced with growattServer `lost=false` and `status=1`       |
| `create_date`               | "2025-11-06"       | date    | Date the plant was registered in Growatt cloud            | Name + date string; consistent with new installation                  |
| `locale`                    | "en-US"            | —       | User interface locale setting                             | Name + IETF language tag format                                       |
| `image_url`                 | "images…jpg"       | —       | URL path to plant image                                   | Name                                                                  |
| `operator` / `installer`    | "0"                | ID      | Assigned operator/installer account IDs (0 = none)        | Name + 0 indicates no associated account                              |
| `user_id`                   | 3648131            | —       | Growatt account user ID of the plant owner                | Name + used in Legacy API plant_list                                  |


### 1.2 plant_details


| Property                                     | Value   | Unit | Description                                                          | Inference                                                            |
| -------------------------------------------- | ------- | ---- | -------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `peak_power`                                 | 10.1    | kWp  | Installed DC peak capacity                                           | Same as plant_list                                                   |
| `plant_type`                                 | 0       | enum | Plant type (0=residential/grid-tied)                                 | Growatt API guide lists plant types; 0 is most common residential    |
| `timezone`                                   | "GMT+1" | —    | Plant local timezone                                                 | Name + matches Poland (CET/CEST)                                     |
| `currency`                                   | "PLN"   | —    | Currency for financial calculations                                  | Name + ISO 4217 code                                                 |
| `locale`                                     | "en_US" | —    | Display locale                                                       | Name                                                                 |
| `inverters`                                  | [{…}]   | —    | Metadata about inverters (manufacturer, model, count) — mostly empty | Name + array of inverter metadata objects                            |
| `dataloggers`                                | [{…}]   | —    | Datalogger (ShineWiFi/LAN dongle) metadata                           | Name + 1 datalogger = 1 ShineWiFi-X unit                             |
| `arrays`                                     | [{…}]   | —    | PV panel array metadata (manufacturer, model, count) — not filled    | Name; optional fields left blank                                     |
| `maxs`                                       | [{…}]   | —    | MAX-type optimizer/combiner box metadata — empty                     | Growatt "MAX" is a product family; metadata not configured           |
| `ownerorganization` / `ownercontact`         | "PLN"   | —    | Owner organization name/contact — currency code used as placeholder  | Values match currency code "PLN", suggesting auto-filled placeholder |
| `description`, `notes`, `address`*, `postal` | ""      | —    | Free-text fields not filled in                                       | All empty strings                                                    |


---

## 2. Device Identity

Properties describing what a device *is* — hardware, firmware, and connectivity. Sourced from `device_list` (discovery) and the top-level fields of `min_detail` (detailed device info).

### 2.1 device_list (Discovery)


| Property           | Value                     | Unit     | Description                                                                      | Inference                                                                          |
| ------------------ | ------------------------- | -------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `device_sn`        | "TSS1F5M04Y"              | —        | Device serial number — primary key for all device API calls                      | Name + used as parameter in min_detail etc.                                        |
| `device_id`        | 1776707                   | —        | Internal numeric device ID in Growatt system                                     | Name + integer                                                                     |
| `type`             | 7                         | enum     | Device category (7=MIN/TLX inverter; 5=SPH/MIX; 3=other; 2=storage)              | growattServer `DeviceType` enum + confirmed by API calling min_* for type 7        |
| `model`            | "S23B08D00T00P0FU01M0078" | —        | Encoded model string (describes hardware configuration: phases, power, features) | Name + Growatt model encoding convention                                           |
| `manufacturer`     | "Growatt"                 | —        | Device manufacturer                                                              | Name                                                                               |
| `datalogger_sn`    | "ZGQ0EZA01C"              | —        | Serial of the ShineWiFi/LAN dongle communicating with the inverter               | Name + same value appears across all devices                                       |
| `last_update_time` | "2026-02-22 09:01:16"     | datetime | Last time the cloud received data from this device                               | Name + matches current run time                                                    |
| `lost`             | false                     | bool     | Whether communication with the device is lost                                    | growattServer docstring explicitly states "mix.status.normal" corresponds to false |
| `status`           | 1                         | enum     | Device operational status (0=standby, 1=generating)                              | Name + 1 during daytime confirms generating                                        |


### 2.2 Identity & Firmware (from min_detail)


| Property               | Value                     | Description                                                               | Inference                                                                                 |
| ---------------------- | ------------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `serialNum`            | "TSS1F5M04Y"              | Inverter serial number                                                    | Name                                                                                      |
| `manufacturer`         | " Hybrid Inverter"        | Confirms unit is a hybrid inverter with battery capability                | Name + value                                                                              |
| `modelText`            | "S23B08D00T00P0FU01M0078" | Full model code                                                           | Name                                                                                      |
| `deviceType`           | 6                         | Internal device type in detail endpoint (differs from device_list type 7) | Name; discrepancy between list (7) and detail (6) is a known inconsistency in Growatt API |
| `innerVersion`         | "DOAA030201"              | Inverter internal firmware version                                        | Name + version string format                                                              |
| `communicationVersion` | "ZBDC-0017"               | Communication/BDC firmware version                                        | Name + "BDC" prefix matches BDC subsystem                                                 |
| `fwVersion`            | "DO1.0"                   | Main inverter firmware version                                            | Name                                                                                      |
| `monitorVersion`       | "ZECA9"                   | Monitoring module firmware version                                        | Name                                                                                      |
| `hwVersion`            | ""                        | Hardware version (not populated)                                          | Name                                                                                      |
| `modbusVersion`        | 1332                      | Modbus protocol version used internally                                   | Name + integer; Growatt Modbus protocol document versioning                               |
| `bmsSoftwareVersion`   | "0"                       | BMS software version (not populated = "0")                                | Name                                                                                      |
| `liBatteryFwVersion`   | "0"                       | Lithium battery firmware version (not populated)                          | Name                                                                                      |
| `bcuVersion`           | "\u0000…-0"               | BCU (Battery Control Unit) firmware (not set — null bytes)                | Name + null bytes indicate field not populated                                            |
| `bdc1Sn`               | "0KNQJ4ED25CT0005"        | BDC1 (primary Battery DC Converter) serial number                         | Name + serial format                                                                      |
| `bdc1Model`            | "4503599627370646"        | BDC1 model ID (numeric)                                                   | Name                                                                                      |
| `bdc1Version`          | "VDAA-9"                  | BDC1 firmware version                                                     | Name                                                                                      |
| `vppVersion`           | 202                       | VPP module version                                                        | Name; "VPP" = Virtual Power Plant feature                                                 |


### 2.3 Physical / Electrical Specs (from min_detail)


| Property                 | Value | Unit       | Description                                                               | Inference                                                          |
| ------------------------ | ----- | ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `pmax` / `opFullwatt`    | 12000 | W          | Rated maximum AC output power (12kW)                                      | Name + value matches "MOD 12KTL3-HU" designation                   |
| `pvNum`                  | 3     | —          | Number of PV string inputs/MPPT channels                                  | Name + value matches `vpv1`, `vpv2`, `vpv3` active in history data |
| `batSysEnergy`           | 50    | kWh        | Battery system total energy capacity                                      | Name + kWh scale                                                   |
| `batteryRatedPower`      | 0     | kW         | Battery rated charge/discharge power (0 = not configured)                 | Name                                                               |
| `batteryType`            | 202   | enum       | Battery chemistry/type code (202 = likely lithium, Growatt internal code) | Name + integer; 0 would be no battery                              |
| `liBatteryManufacturers` | "0"   | —          | Lithium battery manufacturer code (0 = not set)                           | Name                                                               |
| `vnormal`                | 1600  | —          | Normal operating DC bus voltage reference (×0.1 = 160V, or in mV scale)   | Name; "vnormal" = nominal voltage; unit unclear from value alone   |
| `mppt`                   | 2051  | bitmask    | MPPT configuration bitmask (enabled inputs/features)                      | Name + non-sequential integer suggests bitmask encoding            |
| `addr` / `comAddress`    | 1     | —          | Modbus/RS485 communication address                                        | Name + value 1 = default address                                   |
| `timezone`               | 8     | UTC offset | Timezone offset from UTC (8 = UTC+8, China server timezone)               | Name + value matches Asia/Shanghai                                 |


### 2.4 Device Tree / System Membership (from min_detail)


| Property      | Value                | Description                                        | Inference                                          |
| ------------- | -------------------- | -------------------------------------------------- | -------------------------------------------------- |
| `dataLogSn`   | "ZGQ0EZA01C"         | Associated datalogger serial                       | Name                                               |
| `tcpServerIp` | "47.245.131.104"     | IP of Growatt cloud server this device connects to | Name + public IP                                   |
| `treeID`      | "ST_TSS1F5M04Y"      | Device tree node identifier                        | Name + "ST_" prefix convention                     |
| `parentID`    | "LIST_ZGQ0EZA01C_22" | Parent node in device tree (datalogger)            | Name                                               |
| `level`       | 4                    | —                                                  | Depth level in device tree hierarchy               |
| `groupId`     | -1                   | —                                                  | Group assignment (-1 = no group)                   |
| `dtc`         | 5401                 | —                                                  | Device type code (internal Growatt classification) |
| `portName`    | "port_name"          | —                                                  | Connection port identifier (placeholder value)     |


### 2.5 Battery Temperature Limits (from min_detail)


| Property                                    | Description                                                                                     | Inference                                         |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `batTempUpperLimitC` / `batTempUpperLimitD` | Battery temperature upper safety limit, charge (C) and discharge (D) modes (0 = not configured) | Name decomposition: bat + Temp + UpperLimit + C/D |
| `batTempLowerLimitC` / `batTempLowerLimitD` | Battery temperature lower safety limit, charge (C) and discharge (D) modes                      | Name decomposition                                |
| `batSeriesNum` / `batParallelNum`           | Number of battery modules in series / in parallel (0 = auto-detected or not set)                | Name                                              |


---

## 3. Telemetry

Properties describing what the device is *doing* right now. Sourced from `min_energy` (current snapshot) and `min_energy_history` (5-minute intervals). All values are read-only.

### 3.1 Status Summary (from min_detail top-level)


| Property                 | Value                  | Unit     | Description                                                                         | Inference |
| ------------------------ | ---------------------- | -------- | ----------------------------------------------------------------------------------- | --------- |
| `status`                 | 1                      | enum     | Operational status (0=standby, 1=generating, see statusText)                        | Name      |
| `statusText`             | "tlx.status.operating" | —        | Human-readable status label from Growatt i18n key                                   | Name      |
| `lost`                   | false                  | bool     | Communication link OK                                                               | Name      |
| `lastUpdateTimeText`     | "2026-02-22 16:01:16"  | datetime | Last telemetry received (UTC+8 server time)                                         | Name      |
| `eToday`                 | 0                      | kWh      | Energy today (duplicate of eacToday at top level, appears 0 in min_detail snapshot) | Name      |
| `eTotal`                 | 0                      | kWh      | Energy total (duplicate field at top level — not populated here)                    | Name      |
| `energyMonth`            | 0                      | kWh      | Energy this calendar month                                                          | Name      |
| `power`                  | 0                      | W        | Current output power                                                                | Name      |
| `pCharge` / `pDischarge` | 0                      | W        | Battery charge/discharge power at snapshot time                                     | Name      |
| `powerMax`               | ""                     | W        | Historical peak output power (not populated)                                        | Name      |


### 3.2 Grid (AC) Measurements (from min_energy)


| Property                    | Value                 | Unit | Description                                                  | Inference                                                           |
| --------------------------- | --------------------- | ---- | ------------------------------------------------------------ | ------------------------------------------------------------------- |
| `vac1` / `vac2` / `vac3`    | 232.1 / 240.7 / 232.6 | V    | AC grid voltage, phases L1, L2, L3                           | Standard 3-phase naming; values ~230V match EU single-phase nominal |
| `vacRs` / `vacSt` / `vacTr` | 406.6 / 408.4 / 406.2 | V    | Line-to-line voltage: R-S, S-T, T-R (or L1-L2, L2-L3, L3-L1) | "vac" + phase pair; ~400V matches EU 3-phase line voltage           |
| `vacr` / `vacrs`            | 0                     | V    | Additional line voltage measurements (inactive)              | Name analogy                                                        |
| `fac`                       | 50.04                 | Hz   | Grid frequency                                               | "f" + "ac"; ~50Hz EU grid                                           |
| `iac1` / `iac2` / `iac3`    | 1.2 / 1.1 / 1.2       | A    | Grid current per phase                                       | "i" + "ac" + phase number                                           |
| `iacr`                      | 0                     | A    | Additional current measurement (inactive)                    | Name analogy                                                        |
| `pf`                        | 1                     | —    | Power factor (1.0 = unity, ideal)                            | Standard electrical term                                            |
| `pac`                       | 460.6                 | W    | Total AC output power                                        | "p" + "ac"                                                          |
| `pac1` / `pac2` / `pac3`    | 278.5 / 264.7 / 279.1 | W    | AC power per phase                                           | "p" + "ac" + phase                                                  |
| `pacr`                      | 0                     | W    | Additional phase power (inactive)                            | Name analogy                                                        |
| `pacToLocalLoad`            | 492.4                 | W    | Power delivered to local loads                               | growattServer mix_system_status docstring: 'pLocalLoad'             |
| `pacToGridTotal`            | 0                     | kWh  | Cumulative energy exported to grid                           | Name                                                                |
| `pacToUserTotal`            | 0                     | kWh  | Cumulative energy imported from grid                         | Name                                                                |


### 3.3 PV Input Measurements (from min_energy)


| Property                          | Value                 | Unit | Description                                         | Inference                                               |
| --------------------------------- | --------------------- | ---- | --------------------------------------------------- | ------------------------------------------------------- |
| `vpv1` / `vpv2` / `vpv3` / `vpv4` | 348.6 / 0 / 354.2 / 0 | V    | PV string 1–4 voltage (daytime MPP or open-circuit) | "v" + "pv" + number; ~350V typical for string under sun |
| `ipv1` / `ipv2` / `ipv3` / `ipv4` | 0.6 / 0 / 0.8 / 0     | A    | PV string 1–4 current                               | "i" + "pv" + number                                     |
| `ppv1` / `ppv2` / `ppv3` / `ppv4` | 209.1 / 0 / 283.3 / 0 | W    | PV string 1–4 power                                 | "p" + "pv" + number                                     |
| `ppv`                             | 492.4                 | W    | Total PV power                                      | "p" + "pv"                                              |
| `dcVoltage`                       | 0                     | V    | General DC input voltage                            | Name                                                    |


### 3.4 Energy Accumulators (from min_energy)


| Property                                              | Value                | Unit | Description                                                     | Inference                                                              |
| ----------------------------------------------------- | -------------------- | ---- | --------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `eacToday` / `eacTotal`                               | 11.8 / 943.6         | kWh  | AC energy produced today / all-time                             | "e" + "ac" + period; cumulative since installation                     |
| `epv1Today`–`epv3Today`                               | 0.2 / 0 / 0.3        | kWh  | PV energy from string 1/2/3 today                               | "e" + "pv" + string + "Today"                                          |
| `epv1Total`–`epv4Total`                               | 98.5 / 0 / 207.2 / 0 | kWh  | PV energy from string 1/2/3/4 all-time                          | Same pattern                                                           |
| `epvTotal`                                            | 305.7                | kWh  | Total PV energy generated all-time                              | Sum of epv1Total + epv3Total (strings 1 and 3 active)                  |
| `etoGridToday` / `etoGridTotal`                       | 0 / 15.3             | kWh  | Energy exported to grid today / all-time                        | "etoGrid" = energy to grid                                             |
| `etoUserToday` / `etoUserTotal`                       | 0 / 3082.7           | kWh  | Energy imported from grid today / all-time                      | "etoUser" = energy to user (from grid)                                 |
| `elocalLoadToday` / `elocalLoadTotal`                 | 0.5 / 3396.1         | kWh  | Local load consumption today / all-time                         | "elocalLoad" from growattServer MIX docstring                          |
| `eselfToday` / `eselfTotal`                           | 12 / 1048            | kWh  | Self-consumed energy today / all-time (PV or battery, not grid) | "eself" = self-consumption; confirmed by growattServer docstring pself |
| `esystemToday` / `esystemTotal`                       | 12 / 1054.5          | kWh  | Total system energy (self + battery discharge) today / all-time | "esystem" = full system output including battery                       |
| `echargeToday` / `echargeTotal`                       | 12.5 / 904.4         | kWh  | Battery charge energy today / all-time                          | "echarge" = energy into battery                                        |
| `eacChargeToday` / `eacChargeTotal`                   | 13.4 / 921.1         | kWh  | Battery charging via AC/grid today / all-time                   | "eacCharge" = AC-sourced charging                                      |
| `edischargeToday` / `edischargeTotal`                 | 12.5 / 926.2         | kWh  | Battery discharge energy today / all-time                       | "edischarge"                                                           |
| `eex1Today` / `eex1Total` / `eex2Today` / `eex2Total` | 0                    | kWh  | External port (EX1/EX2) energy — not used                       | "eex" = energy export/extension port; zero = no external device        |
| `pself`                                               | 492.4                | W    | Current self-consumption power                                  | "p" + "self"; from growattServer MIX docstring                         |
| `psystem`                                             | 492.4                | W    | Current total system power output                               | "p" + "system"                                                         |


### 3.5 Battery — BMS (from min_energy)


| Property                                | Value     | Unit    | Description                                                               | Inference                                       |
| --------------------------------------- | --------- | ------- | ------------------------------------------------------------------------- | ----------------------------------------------- |
| `bmsSoc` / `bdc1Soc`                    | 20 / 20   | %       | Battery state of charge (BMS reading / BDC1 reading agree → reliable)     | "Soc" = State of Charge; two sources agree      |
| `bdc2Soc`                               | 3         | %       | SoC at BDC2 (auxiliary subsystem or secondary battery)                    | Same naming; differs from bdc1Soc               |
| `bmsSoh`                                | 100       | %       | Battery state of health (100% = like new, no degradation yet)             | "Soh" = State of Health; standard BMS metric    |
| `bmsVbat`                               | 0         | V       | Battery terminal voltage from BMS (0 in min_energy standby snapshot)      | "bms" + "Vbat"; zero at night                   |
| `bmsIbat`                               | 0         | A       | Battery current from BMS (positive=charging, negative=discharging)        | "bms" + "Ibat"                                  |
| `bmsTemp1Bat`                           | 0         | °C      | Battery pack temperature sensor 1 (0 in standby snapshot)                 | "bms" + "Temp" + "Bat"                          |
| `bmsCvVolt`                             | 0         | V       | Battery constant-voltage charge setpoint (0 in standby)                   | "bms" + "Cv" (constant voltage) + "Volt"        |
| `bmsMaxCurr`                            | 0         | A       | Battery maximum allowed current from BMS                                  | "bms" + "MaxCurr"                               |
| `bmsFaultType`                          | 0         | bitmask | BMS fault code (0=no fault)                                               | "bms" + "FaultType"                             |
| `bmsWarnCode` / `bmsWarn2`              | 0         | bitmask | BMS warning codes                                                         | Name                                            |
| `bmsError2` / `bmsError3` / `bmsError4` | 0         | bitmask | BMS error registers                                                       | Name                                            |
| `bmsInfo`                               | 0         | bitmask | BMS status info bitmask                                                   | Name; 464 in history data = some bits set       |
| `bmsPackInfo`                           | 0         | bitmask | Battery pack status                                                       | Name                                            |
| `bmsMcuVersion` / `bmsFwVersion`        | "0"       | —       | BMS MCU and firmware versions (0 = not detected)                          | Name                                            |
| `bmsStatus`                             | 0         | enum    | BMS operational state (0=idle/not connected)                              | Name                                            |
| `bmsGaugeRM`                            | 0         | Ah      | Remaining capacity from fuel gauge IC                                     | "GaugeRM" = gauge remaining mAh; 0 = not active |
| `bmsMaxCellVolt`                        | 0         | V       | Highest individual cell voltage in pack                                   | Name                                            |
| `bmsVdelta`                             | 0         | V       | Voltage spread between highest and lowest cell                            | "Vdelta" = voltage delta                        |
| `bmsIcycle`                             | 0         | —       | Charge cycle count                                                        | "Icycle" = integer cycle count                  |
| `bmsUsingCap`                           | 0         | Ah      | Capacity currently in use                                                 | Name                                            |
| `bmsCommunicationType`                  | 0         | enum    | Battery-BMS communication protocol (0=CAN/inactive)                       | Name                                            |
| `bmsIosStatus`                          | 0         | bitmask | BMS IO pin status register                                                | Name                                            |
| `batterySN`                             | "\u0000…" | —       | Battery serial number (null bytes = not set / battery SN not transmitted) | Name + null bytes = empty string in firmware    |
| `batteryNo`                             | 0         | —       | Battery module index (0 = first/only module)                              | Name                                            |
| `batSn`                                 | ""        | —       | Alternate battery serial field (empty)                                    | Name                                            |


### 3.6 Battery — BDC1 (primary Battery DC Converter, from min_energy)


| Property                                 | Value | Unit    | Description                                        | Inference                                                                         |
| ---------------------------------------- | ----- | ------- | -------------------------------------------------- | --------------------------------------------------------------------------------- |
| `bdc1Vbat`                               | 730.4 | V       | Battery voltage at BDC1 terminals (HV battery bus) | "bdc1" + "Vbat"; ~730V = HV lithium pack                                          |
| `bdc1Ibat`                               | 0     | A       | Battery current at BDC1                            | "bdc1" + "Ibat"                                                                   |
| `bdc1Vbus1`                              | 0     | V       | BDC1 DC bus voltage rail 1 (high-side)             | "Vbus" = DC bus voltage; in history ~722V = HV DC link                            |
| `bdc1Vbus2`                              | 0     | V       | BDC1 DC bus voltage rail 2 (low-side/split)        | Same + second rail                                                                |
| `bdc1Ibb`                                | 0     | A       | BDC1 boost inductor current (LLC boost stage)      | "Ibb" = inductor/boost bridge current in DC-DC topology                           |
| `bdc1Illc`                               | 0     | A       | BDC1 LLC resonant converter current                | "Illc" = current in LLC (Inductor-Inductor-Capacitor) resonant converter topology |
| `bdc1Temp1` / `bdc1Temp2`                | 0     | °C      | BDC1 temperature sensors (PCB and heatsink)        | "bdc1" + "Temp" + number                                                          |
| `bdc1Status`                             | 0     | enum    | BDC1 operational status                            | Name                                                                              |
| `bdc1Mode`                               | 0     | enum    | BDC1 mode (0=load first/standby)                   | Name                                                                              |
| `bdc1FaultType`                          | 0     | bitmask | BDC1 fault code                                    | Name                                                                              |
| `bdc1WarnCode`                           | 0     | bitmask | BDC1 warning code                                  | Name                                                                              |
| `bdc1ChargePower` / `bdc1DischargePower` | 0     | W       | BDC1 active charge/discharge power                 | Name                                                                              |
| `bdc1ChargeTotal`                        | 904.4 | kWh     | BDC1 cumulative charge energy all-time             | Name; matches echargeTotal                                                        |
| `bdc1DischargeTotal`                     | 926.2 | kWh     | BDC1 cumulative discharge energy all-time          | Name; matches edischargeTotal                                                     |


### 3.7 Battery — BDC2 (secondary converter, from min_energy)

BDC2 appears to be an auxiliary 12V supply chain internal to the inverter, not a second battery. See anomalies at end of this document.


| Property                                 | Value        | Unit    | Description                                                                                                                 | Inference                                                                          |
| ---------------------------------------- | ------------ | ------- | --------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `bdc2Vbat`                               | 0            | V       | Voltage at BDC2 battery terminals (0 in standby; ~12-13V in history = 12V auxiliary supply)                                 | Name; 12V in history data matches aux electronics supply voltage                   |
| `bdc2Ibat`                               | 0            | A       | BDC2 current (11.7A in history = likely internal bootstrap current, not a real battery)                                     | Name                                                                               |
| `bdc2Vbus1` / `bdc2Vbus2`                | 0 / 10       | V       | BDC2 bus voltages                                                                                                           | Name                                                                               |
| `bdc2Ibb`                                | 10           | A       | BDC2 boost bridge current (constant 10A in history — possibly internal reference/monitoring)                                | Name; constant value regardless of load suggests it's an internal monitoring value |
| `bdc2Illc`                               | 0            | A       | BDC2 LLC current                                                                                                            | Name                                                                               |
| `bdc2Temp1` / `bdc2Temp2`                | 0 / 104      | °C      | BDC2 temperatures (Temp2=104°C in history is suspicious — may be raw ADC, uncalibrated sensor, or internal reference point) | Name; 104°C would be above thermal shutdown if real — likely raw register value    |
| `bdc2Status`                             | 0            | enum    | BDC2 status                                                                                                                 | Name                                                                               |
| `bdc2Mode`                               | 0            | enum    | BDC2 mode                                                                                                                   | Name                                                                               |
| `bdc2FaultType`                          | 7            | bitmask | BDC2 fault/status code                                                                                                      | Name; may be normal operational state for auxiliary subsystem                      |
| `bdc2WarnCode`                           | 1            | bitmask | BDC2 warning code                                                                                                           | Name                                                                               |
| `bdc2ChargePower` / `bdc2DischargePower` | 0            | W       | BDC2 charge/discharge power                                                                                                 | Name                                                                               |
| `bdc2ChargeTotal` / `bdc2DischargeTotal` | 745.4 / 3.29 | kWh     | BDC2 cumulative charge/discharge energy                                                                                     | Name; different subsystem tracks independently                                     |
| `bdc2Soc`                                | 3            | %       | SoC at BDC2 (auxiliary subsystem)                                                                                           | Name                                                                               |


### 3.8 DC Bus / Internal (from min_energy)


| Property          | Value | Unit | Description                                                                 | Inference                                                            |
| ----------------- | ----- | ---- | --------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `pBusVoltage`     | 366.1 | V    | Positive DC bus voltage (main inverter DC link)                             | Name; ~366V during generation                                        |
| `nBusVoltage`     | 365   | V    | Negative DC bus voltage rail (split DC bus)                                 | Name; same pattern                                                   |
| `bdcVbus2Neg`     | 0     | V    | BDC negative bus voltage                                                    | Name                                                                 |
| `bdcBusRef`       | 7454  | —    | BDC bus voltage reference setpoint (likely ×0.1 = 745V, or raw DAC count)   | Name; "Ref" = reference/setpoint; correlates with DC bus load        |
| `bdcStatus`       | 1     | enum | Overall BDC status                                                          | Name; 1 = active during generation                                   |
| `bdcDerateReason` | 0     | enum | Reason for power derating (0=none; 1 in history = frequency/voltage derate) | Name; 1 in history matches overFreDropPoint active during generation |
| `bdcFaultSubCode` | 0     | —    | BDC fault sub-code                                                          | Name                                                                 |
| `bdcWarnSubCode`  | 0     | —    | BDC warning sub-code                                                        | Name                                                                 |


### 3.9 EPS / Emergency Power Supply (from min_energy)

EPS is inactive on this installation (`epsFunEn = 0`). All values read 0 during normal grid-connected operation.


| Property                                     | Value | Unit | Description                                        | Inference             |
| -------------------------------------------- | ----- | ---- | -------------------------------------------------- | --------------------- |
| `epsVac1` / `epsVac2` / `epsVac3`            | 0     | V    | EPS output AC voltage per phase (0 = EPS inactive) | "eps" + "Vac" + phase |
| `epsIac1` / `epsIac2` / `epsIac3`            | 0     | A    | EPS output current per phase                       | "eps" + "Iac" + phase |
| `epsPac` / `epsPac1` / `epsPac2` / `epsPac3` | 0     | W    | EPS output power (total + per phase)               | "eps" + "Pac"         |
| `epsFac`                                     | 0     | Hz   | EPS output frequency                               | "eps" + "Fac"         |
| `epsPf`                                      | 0     | —    | EPS output power factor                            | "eps" + "Pf"          |


### 3.10 Temperatures (from min_energy)


| Property          | Value | Unit | Description                                                       | Inference                               |
| ----------------- | ----- | ---- | ----------------------------------------------------------------- | --------------------------------------- |
| `temp1` / `temp3` | 29.3  | °C   | Ambient / PCB temperature sensor (indoor cabinet temperature)     | Higher during generation                |
| `temp2`           | 53    | °C   | Heat sink or inverter core temperature (warmer during generation) | Higher value during power output        |
| `temp4`           | 0     | °C   | Additional temperature sensor (not active/connected)              | Zero = sensor not fitted or not reading |
| `temp5`           | 31.5  | °C   | Another active temperature sensor location                        | Non-zero confirms active sensor         |


### 3.11 Protection / Safety (from min_energy)


| Property                         | Value | Unit    | Description                                                                                     | Inference                                                                      |
| -------------------------------- | ----- | ------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `iso`                            | 231   | kΩ      | Insulation resistance between PV strings and earth (adequate; typical alarm threshold is <30kΩ) | "iso" = isolation/insulation resistance; standard PV safety metric             |
| `gfci`                           | 0     | mA      | Ground fault current (0 = no fault)                                                             | "gfci" = Ground Fault Circuit Interrupter; standard PV safety check            |
| `dciR` / `dciS` / `dciT`         | 0     | mA      | DC injection current per AC phase (R/S/T); must stay near zero to avoid transformer saturation  | "dci" = DC injection current + phase letter; required to monitor per IEC 61727 |
| `sysFaultWord`                   | 0     | bitmask | System fault register (main)                                                                    | Name; 0 = no active faults                                                     |
| `sysFaultWord1`–`sysFaultWord7`  | 0     | bitmask | Additional system fault registers (extended fault codes)                                        | Name; multiple registers needed for full fault bitmap                          |
| `faultType` / `faultType1`       | 0     | bitmask | Fault type code                                                                                 | Name                                                                           |
| `warnCode` / `warnCode1`         | 0     | bitmask | Warning code                                                                                    | Name                                                                           |
| `newWarnCode` / `newWarnSubCode` | 0     | bitmask | Newer format warning codes                                                                      | Name + "new" prefix = revised code structure                                   |


### 3.12 System Metrics (from min_energy)


| Property                 | Value     | Unit | Description                                                                                                     | Inference                                                                                          |
| ------------------------ | --------- | ---- | --------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `deratingMode`           | 0         | enum | Current power derating mode (0=none)                                                                            | Growatt Modbus protocol V3.14 includes DeratingMode register                                       |
| `realOPPercent`          | 3         | %    | Real output power as % of max                                                                                   | Name + % range                                                                                     |
| `loadPercent`            | 0         | %    | Load as % of inverter capacity                                                                                  | Name                                                                                               |
| `opFullwatt`             | 12000     | W    | Rated max output power (12kW)                                                                                   | Name + value                                                                                       |
| `invDelayTime`           | 60        | s    | Grid reconnection delay (60s = standard EU requirement after grid disturbance)                                  | Name; 60s is typical grid code reconnection delay                                                  |
| `timeTotal`              | 988413.6  | s    | Total inverter operating time counter (≈11.4 days uptime or a reset counter)                                    | Name                                                                                               |
| `totalWorkingTime`       | 0         | —    | Alternate working time counter (0 = not used or separate metric)                                                | Name                                                                                               |
| `status`                 | 1         | enum | Inverter status (0=standby, 1=generating)                                                                       | Name                                                                                               |
| `statusText`             | "Normal"  | —    | Human-readable status                                                                                           | Name                                                                                               |
| `errorText` / `warnText` | "Unknown" | —    | Active error/warning text (firmware fallback when no active code)                                               | Name                                                                                               |
| `lost`                   | true      | bool | In min_energy: communication shown as lost at time of snapshot (inverter in night standby, datalogger sleeping) | Name; `true` here even though device_list shows `lost=false` — may be a snapshot timing difference |
| `bgridType`              | 0         | enum | Grid connection type in energy snapshot (0 = single-phase report format?)                                       | Name; min_detail has bgridType=1 (3-phase)                                                         |
| `again` / `isAgain`      | false     | bool | Retry flag (data re-sent because previous upload failed)                                                        | Name; "isAgain" in history, "again" in energy                                                      |
| `withTime`               | false     | bool | Whether time information is embedded in data                                                                    | Name                                                                                               |
| `day`                    | ""        | —    | Day identifier for the record (empty = current day)                                                             | Name                                                                                               |
| `address`                | 0         | —    | Modbus address in this data context                                                                             | Name                                                                                               |


### 3.13 External Ports (from min_energy)


| Property           | Value | Unit | Description                                                                            | Inference                                                                      |
| ------------------ | ----- | ---- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `pex1` / `pex2`    | 0     | W    | External port 1/2 power (EX ports — for additional generation sources like generators) | "pex" = power from external source; growattServer MIX docstring includes 'pex' |
| `dryContactStatus` | 0     | bool | Dry contact relay current state (0=open)                                               | Name                                                                           |


### 3.14 Debug / Internal (from min_energy)


| Property     | Value                                  | Description                                                                                                                                                  | Inference                                                                    |
| ------------ | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `debug1`     | "0，0，0，0，1300，10，1，49720"              | Internal debug register dump (comma-separated, Chinese comma ，). Contains raw firmware state variables.                                                      | Name + "debug" prefix; Chinese comma separators indicate raw firmware string |
| `debug2`     | "3，1776，36695，33305，32795，0，11010，243" | Second debug register dump                                                                                                                                   | Same                                                                         |
| `calendar`   | Java Calendar object                   | Java `Calendar` object from Growatt's backend — contains timestamp in UTC+8, timezone "Asia/Shanghai". Includes Gregorian calendar reform date (1582-10-15). | Object structure matches Java `Calendar.toJSON()` or similar serialization   |
| `createTime` | 1771688219                             | Unix ms                                                                                                                                                      | Record creation timestamp on Growatt server (epoch milliseconds)             |


### 3.15 Historical Data Structure (min_energy_history)


| Property             | Value        | Description                                                                                 | Inference                                              |
| -------------------- | ------------ | ------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `next_page_start_id` | 21           | Pagination cursor for next page request                                                     | Name; typical cursor-based pagination                  |
| `tlx_sn`             | "TSS1F5M04Y" | Device serial echoed back                                                                   | Name                                                   |
| `datas`              | [array]      | Array of historical records, each with the same fields as min_energy, at 5-minute intervals | Name + array of per-timestamp objects                  |
| `count`              | 219          | Total number of records available for the queried day                                       | Name; 219 records × 5 min ≈ 18.25h of data for the day |
| `datalogger_sn`      | "ZGQ0EZA01C" | Datalogger serial                                                                           | Name                                                   |


Each record in `datas` contains the same fields as `min_energy` plus:


| Property     | Description                                           | Inference          |
| ------------ | ----------------------------------------------------- | ------------------ |
| `time`       | Timestamp of this record (e.g. "2026-02-21 16:43:38") | Name               |
| `calendar`   | Java Calendar object for this record's timestamp      | Same as min_energy |
| `createTime` | Server-side creation timestamp (epoch ms)             | Name               |


---

## 4. Configuration

Configured parameters — not real-time measurements but operating rules. Sourced from `min_detail.tlxSetbean`. These fields describe what the device is *set to*. All write operations target fields in this section via `min_write_parameter` or `min_write_time_segment`.

### 4.1 Time-of-Use Schedule


| Property                                  | Example value          | Description                                                                                                                                                                        | Inference                                                                                                                                                    |
| ----------------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `yearTime1`–`yearTime9`                   | "2_0_26_30_30_0_0"     | 9 time-of-use (TOU) slots for a yearly schedule. Format: `mode_enable_startH_startM_stopH_stopM_extra`. yearTime1="2_0_26_30_30_0_0" = mode 2 (grid first?), enabled, 06:30–30:00? | growattServer `read_time_segments` parses `time1Mode`, `forcedTimeStart`, `forcedTimeStop` from same bean; "yearTime" fields are alternate schedule encoding |
| `time1Mode`–`time9Mode`                   | 1, 2, 0, …             | Operating mode for TOU slot 1–9 (0=Load First, 1=Battery First, 2=Grid First)                                                                                                      | growattServer min_tlx_settings.md: batt_mode 0=Load First, 1=Battery First, 2=Grid First                                                                     |
| `forcedTimeStart1`–`forcedTimeStart9`     | "13:30", "11:0", "0:0" | Start time of each forced charge/discharge window (HH:MM)                                                                                                                          | growattServer `read_time_segments` reads these fields by name                                                                                                |
| `forcedTimeStop1`–`forcedTimeStop9`       | "15:0", "15:0", "0:0"  | End time of each forced window                                                                                                                                                     | Same                                                                                                                                                         |
| `forcedStopSwitch1`–`forcedStopSwitch9`   | 0                      | Enable/disable each forced window (0=disabled, 1=enabled)                                                                                                                          | growattServer `enabled = int(enabled_raw) == 1`                                                                                                              |
| `season1Time1`–`season4Time9`             | "0_0_0_0_0_0_0"        | Seasonal schedule slots (4 seasons × 9 slots) in same format as yearTime                                                                                                           | Name + same encoded format as yearTime                                                                                                                       |
| `season1MonthTime`–`season4MonthTime`     | "0_0_0"                | Month range for each season definition                                                                                                                                             | Name + 3 values suggest start month, end month, something                                                                                                    |
| `special1Time1`–`special2Time9`           | "0_0_0_0_0_0"          | Special date schedule slots (2 special periods × 9 slots)                                                                                                                          | Name + same format                                                                                                                                           |
| `special1MonthTime` / `special2MonthTime` | "0_0_0"                | Month/date range for special periods                                                                                                                                               | Name                                                                                                                                                         |
| `yearMonthTime`                           | "null"                 | Year-level month override                                                                                                                                                          | Name                                                                                                                                                         |


### 4.2 Battery Charge/Discharge Settings


| Property                                         | Value | Unit | Description                                                                   | Inference                                                          |
| ------------------------------------------------ | ----- | ---- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `chargePowerCommand`                             | 100   | %    | Max battery charging power as % of rated                                      | growattServer `charge_power` parameter; 100% = full power charging |
| `disChargePowerCommand`                          | 100   | %    | Max battery discharging power as % of rated                                   | Name + companion to chargePowerCommand                             |
| `onGridDischargeStopSOC`                         | 20    | %    | Stop discharging battery when SoC drops to this level (grid-connected mode)   | growattServer `discharge_stop_soc` parameter                       |
| `ubAcChargingStopSOC`                            | 80    | %    | Stop AC (grid) charging when battery reaches this SoC                         | Name + "AcCharging" + "StopSOC"                                    |
| `acChargeEnable`                                 | 1     | bool | Allow grid to charge battery (1=enabled)                                      | Name + growattServer `ac_charge` parameter                         |
| `wchargeSOCLowLimit`                             | 100   | %    | Winter mode max charge SoC                                                    | Name; "w" = winter mode                                            |
| `wdisChargeSOCLowLimit`                          | 10    | %    | Winter mode discharge stop SoC                                                | Name; consistent with onGridDischargeStopSOC                       |
| `vbatStartForDischarge` / `vbatStopForDischarge` | 0     | V    | Voltage thresholds to start/stop discharge (0 = SoC-based, not voltage-based) | Name                                                               |
| `vbatStartforCharge` / `vbatStopForCharge`       | 0     | V    | Voltage thresholds to start/stop charging                                     | Name                                                               |
| `vbatWarning` / `vbatWarnClr`                    | 0     | V    | Low battery voltage warning/clear thresholds                                  | Name                                                               |
| `floatChargeCurrentLimit`                        | 0     | A    | Float charge current limit (0 = auto)                                         | Name                                                               |


### 4.3 Grid Export / Import Limits


| Property                  | Value | Unit | Description                                     | Inference                                   |
| ------------------------- | ----- | ---- | ----------------------------------------------- | ------------------------------------------- |
| `exportLimit`             | 0     | bool | Enable export power limit (0=disabled)          | Name + companion exportLimitPowerRate       |
| `exportLimitPowerRate`    | 0     | %    | Export power cap as % of inverter rated power   | Name + Growatt export limit feature         |
| `exportLimitPowerRateStr` | ""    | —    | String representation of export limit (not set) | Name                                        |
| `backFlowSingleCtrl`      | 0     | bool | Single-phase backflow prevention control        | Name; relevant for single-phase anti-export |
| `backflowDefaultPower`    | 0     | W    | Default power setpoint for backflow prevention  | Name                                        |


#### How the Export Limit Feature Works

The export limit function controls how much power the inverter is allowed to push back into the grid. It requires a **physical Growatt meter** installed between the grid connection and household loads, communicating with the inverter via **RS485**. Without the meter, the inverter has no real-time feedback on actual export flow.

- Single-phase systems: use **Growatt SPM** meter
- Three-phase systems: use **Growatt TPM** meter

> Sources: [Growatt Export Limitation Guide](../docs/references/growatt-export-limitation-guide.pdf) · [Raystech TLX Export Limit Guide](../docs/references/tlx-export-limit.pdf)

`**exportLimit` (Set Exportlimit — Enable Meter)**

Master on/off switch for the feature. When `1`, the inverter reads real-time export from the meter and throttles its output to stay within the configured threshold. When `0`, export is unrestricted.

`**exportLimitPowerRate` (Limit threshold)**

The cap value. Can be expressed as:

- **Percent** — % of inverter rated power (e.g. `50` = max 6 kW export on a 12 kW inverter; `0` = zero export)
- **Power** — absolute watts (e.g. `3000` = max 3000 W to grid)

The ShineServer UI exposes a unit dropdown (Percent / Power) that maps to how this value is interpreted. In the API, the raw value is always stored as a percentage of rated power (`exportLimitPowerRate`).

Example: if limit is 3000 W and 1 kW load is added, the inverter outputs 4 kW total (1 kW load + 3 kW to grid).

`**backflowDefaultPower` (Default Power After Exportlimit Failure)**

Safety fallback. If the meter loses RS485 communication, the inverter no longer has real-time export data. This value defines the **maximum output power** in that failure state.

- `0` = zero export when meter fails (most restrictive / safest for grid operator)
- Non-zero = allow up to N watts even without meter feedback

`**backFlowSingleCtrl` (Phase Level)**

For 3-phase inverters, controls whether the export limit is enforced per-phase or on the total system sum:

- `0` (Disable) = **total/system level** — the inverter sums all 3 phases. Standard for Poland and most EU markets (EN 50549).
- `1` (Enable) = **per-phase level** — each phase is controlled independently. Required in some countries (e.g. Czech Republic).

#### Current device config (TSS1F5M04Y as of 2026-02-22)


| Setting                | Value | Meaning                                               |
| ---------------------- | ----- | ----------------------------------------------------- |
| `exportLimit`          | 0     | Export limiting **disabled** — surplus exports freely |
| `exportLimitPowerRate` | 0     | 0% threshold (dormant)                                |
| `backflowDefaultPower` | 0     | 0 W fallback on meter failure (dormant)               |
| `backFlowSingleCtrl`   | 0     | Total system assessment — correct for Poland          |


### 4.4 Power Quality & Grid Protection


| Property                                       | Value        | Unit  | Description                                                                          | Inference                                                                              |
| ---------------------------------------------- | ------------ | ----- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| `frequencyHighLimit` / `frequencyLowLimit`     | 50.05 / 49.0 | Hz    | Grid frequency operating window; inverter disconnects outside                        | Name + EU grid frequency 50Hz standard                                                 |
| `voltageHighLimit` / `voltageLowLimit`         | 440 / 340    | V     | Grid voltage operating window (line-to-line for 3-phase EU 400V)                     | Name + 440/340V brackets the EU 400V 3-phase spec                                      |
| `overVolt3` / `underVolt3`                     | 460 / 338.6  | V     | Overvoltage/undervoltage trip thresholds                                             | Name + standard protection settings above/below operating window                       |
| `overVoltTime1`–`overVoltTime3`                | 140          | ms    | Response time for overvoltage protection levels                                      | Name + milliseconds scale matches grid codes                                           |
| `underVoltTime1`–`underVoltTime3`              | 1400         | ms    | Response time for undervoltage protection                                            | Name                                                                                   |
| `overFreq3` / `underFreq3`                     | 52.0 / 47.5  | Hz    | Over/underfrequency trip thresholds                                                  | Name + typical EU grid code values                                                     |
| `overFreqTime1`–`overFreqTime3`                | 400          | ms    | Response time for overfrequency protection                                           | Name                                                                                   |
| `underFreqTime1`–`underFreqTime3`              | 400          | ms    | Response time for underfrequency protection                                          | Name                                                                                   |
| `uwHVRTEE` / `uwHVRT2EE`                       | 440 / 460    | V     | High Voltage Ride-Through thresholds (HVRT), level 1 and 2                           | "HVRT" = High Voltage Ride-Through, standard grid code feature; two levels of severity |
| `uwLVRTEE` / `uwLVRT2EE`                       | 340 / 338.6  | V     | Low Voltage Ride-Through thresholds                                                  | "LVRT" = Low Voltage Ride-Through                                                      |
| `uwHFRTEE` / `uwHFRT2EE`                       | 52.0         | Hz    | High Frequency Ride-Through threshold                                                | "HFRT" = High Frequency Ride-Through                                                   |
| `uwLFRTEE` / `uwLFRT2EE`                       | 47.5         | Hz    | Low Frequency Ride-Through threshold                                                 | "LFRT" = Low Frequency Ride-Through                                                    |
| `gridHVReduceLoadLow` / `gridHVReduceLoadHigh` | -0.1         | —     | Grid high-voltage power reduction trigger (likely % or normalized)                   | Name; "HVReduceLoad" = reduce output when HV detected                                  |
| `overFreLoRedSlope` / `overFreDropPoint`       | 40 / 50.2    | %, Hz | Frequency-watt curve: slope (%) and frequency trigger point (Hz) for power reduction | Name; "FreLo" = frequency low; standard grid droop response                            |
| `antiIslandEnable`                             | -1           | enum  | Anti-islanding protection (-1 may mean auto/firmware-default)                        | Name; anti-islanding is mandatory in grid codes                                        |
| `gridCode`                                     | 8968         | enum  | Numeric code for selected national grid standard                                     | Name + integer; Growatt uses numeric grid code IDs                                     |
| `safetyNum`                                    | "23"         | enum  | Safety standard number (likely internal code for EN/IEC standard)                    | Name + integer string                                                                  |
| `safetyCorrespondNum`                          | 5            | —     | Sub-number within safety standard                                                    | Name                                                                                   |


> **Do not modify these parameters via the API.** Grid protection settings are configured by certified installers to comply with national grid codes. Incorrect values can cause grid disconnection, regulatory violations, or unsafe conditions. See `docs/parameters/safety-constraints.md`.

### 4.5 Reactive Power (Q(V) Curve)


| Property                             | Value     | Unit | Description                                                                           | Inference                                                      |
| ------------------------------------ | --------- | ---- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `qvH1` / `qvH2`                      | 424 / 432 | V    | Q(V) high-voltage breakpoints: voltage at which reactive power injection starts/maxes | Name; Q(V) reactive power curve is required by many grid codes |
| `qvL1` / `qvL2`                      | 376 / 368 | V    | Q(V) low-voltage breakpoints for reactive power absorption                            | Name                                                           |
| `qPercentMax`                        | 48.4      | %    | Maximum reactive power as % of rated                                                  | Name                                                           |
| `qvInLVPowerPer` / `qvOutHVPowerPer` | 48.4      | %    | Reactive power percentage at low/high voltage breakpoints                             | Name                                                           |
| `vActiveCutoffPowerPer`              | 0         | %    | Voltage-active power cutoff percentage                                                | Name                                                           |
| `reactiveOutputEnable`               | 0         | bool | Enable reactive power output control                                                  | Name                                                           |
| `reactiveRate`                       | 0         | %    | Reactive power rate setting                                                           | Name                                                           |
| `pflinep1_pf`–`pflinep4_pf`          | 1         | —    | Power factor at PF curve breakpoints (1.0 = unity)                                    | Name; "pfline" = power factor curve                            |
| `pflinep1_lp`–`pflinep4_lp`          | 255       | %    | Load power at each PF curve breakpoint (255 = 100%)                                   | Name                                                           |
| `pfModel`                            | 0         | enum | Power factor control model (0 = off/default)                                          | Name                                                           |
| `activePowerEnable`                  | 0         | bool | Active power control enable                                                           | Name                                                           |
| `activeRate`                         | 100       | %    | Active power rate (scaling factor for active power control)                           | Name                                                           |
| `puEnable`                           | 1         | bool | Per-unit power control enable                                                         | Name                                                           |


### 4.6 Operating Mode & Advanced


| Property                                                           | Value  | Description                                                                               | Inference                                                                                                                      |
| ------------------------------------------------------------------ | ------ | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `onOff`                                                            | 1      | Inverter on/off switch (1=on)                                                             | Name                                                                                                                           |
| `onGridMode`                                                       | 0      | On-grid mode variant (0=standard)                                                         | Name                                                                                                                           |
| `bsystemWorkMode`                                                  | 0      | Battery system work mode                                                                  | Name                                                                                                                           |
| `bgridType`                                                        | 1      | Grid type (1=3-phase)                                                                     | Name; 1-phase would be 0                                                                                                       |
| `rrcrEnable`                                                       | 1      | RRCR (Ripple Control Relay Receiver) enable — responds to grid operator frequency control | "RRCR" is a grid-side control signal used in some EU countries                                                                 |
| `priorityChoose`                                                   | 53     | Battery priority choice (bitmask or enum)                                                 | Name; observed as constant                                                                                                     |
| `operatingMode`                                                    | 0      | Operating mode (0=auto/default)                                                           | Name                                                                                                                           |
| `uwSysWorkMode`                                                    | 0      | System work mode (0=load first)                                                           | growattServer API docstring references similar field; Growatt operating modes: 0=Load First confirmed by Growatt official blog |
| `demandManageEnable`                                               | 0      | Demand management feature enable                                                          | Name                                                                                                                           |
| `uwDemandMgtRevsePowerLimit`                                       | 3000   | W — Demand management reverse power limit                                                 | Name                                                                                                                           |
| `uwDemandMgtDownStrmPowerLimit`                                    | 3000   | W — Demand management downstream power limit                                              | Name                                                                                                                           |
| `uwAcChargingMaxPowerLimit`                                        | 12     | kW — Maximum AC charging power                                                            | Name                                                                                                                           |
| `peakShavingEnable`                                                | 0      | Peak shaving feature enable                                                               | Name                                                                                                                           |
| `showPeakShaving`                                                  | 1      | Show peak shaving in UI (1=yes)                                                           | Name                                                                                                                           |
| `ubPeakShavingBackupSOC`                                           | 50     | % — Backup SoC reserved during peak shaving                                               | Name                                                                                                                           |
| `winModeFlag`                                                      | 0      | Winter mode active flag                                                                   | Name                                                                                                                           |
| `winModeStartTime` / `winModeEndTime`                              | "null" | Winter mode schedule window                                                               | Name                                                                                                                           |
| `winModeOnGridDischargeStopSOC` / `winModeOffGridDischargeStopSOC` | 0      | % — Winter mode discharge stop SoC (on/off grid)                                          | Name                                                                                                                           |
| `winOnGridSOC` / `winOffGridSOC`                                   | 0      | % — Winter mode target SoC                                                                | Name                                                                                                                           |
| `maintainModeRequest`                                              | 0      | Maintenance mode requested (0=no)                                                         | Name                                                                                                                           |
| `maintainModeStartTime`                                            | "null" | When maintenance mode starts                                                              | Name                                                                                                                           |
| `epsFunEn`                                                         | 0      | EPS (Emergency Power Supply) function enable                                              | Name; 0=disabled means no backup power output configured                                                                       |
| `epsFreqSet` / `epsVoltSet`                                        | 0      | EPS output frequency/voltage setpoints                                                    | Name                                                                                                                           |
| `sleepOffGridEnable`                                               | 0      | Sleep mode when off-grid                                                                  | Name                                                                                                                           |
| `powerDownEnable`                                                  | 0      | Automatic power-down enable                                                               | Name                                                                                                                           |
| `synEnable`                                                        | 0      | Generator synchronization enable                                                          | Name                                                                                                                           |
| `genCtrl` / `genRatedPower` / `genChargeEnable`                    | 0      | Generator control, rated power, and charge enable (no generator connected)                | Name                                                                                                                           |
| `dryContactFuncEn`                                                 | 0      | Dry contact relay function enable                                                         | Name                                                                                                                           |
| `dryContactOnRate` / `dryContactOffRate`                           | 40     | % — Dry contact relay on/off power thresholds                                             | Name                                                                                                                           |
| `dryContactPower`                                                  | 50     | W — Dry contact relay power setpoint                                                      | Name                                                                                                                           |
| `exterCommOffGridEn`                                               | 0      | External communication off-grid enable                                                    | Name                                                                                                                           |
| `limitDevice`                                                      | 0      | Energy limit device ID (0=none)                                                           | Name                                                                                                                           |
| `enableNLine`                                                      | 0      | Enable neutral line output                                                                | Name                                                                                                                           |
| `loadingRate` / `restartLoadingRate`                               | 10     | % — Power ramp-up rate on start / restart                                                 | Name                                                                                                                           |
| `delayTime`                                                        | 15000  | ms — Reconnection delay time (15s = 15,000ms)                                             | Name                                                                                                                           |
| `restartTime`                                                      | 60     | s — Restart delay                                                                         | Name                                                                                                                           |
| `prePto`                                                           | 0      | Pre-PTO (Permission to Operate) flag                                                      | Name; "PTO" is utility interconnection approval                                                                                |
| `lcdLanguage`                                                      | 6      | enum — Display language code (6 = likely English)                                         | Name                                                                                                                           |
| `onGridStatus`                                                     | 0      | On-grid status                                                                            | Name                                                                                                                           |
| `region`                                                           | 0      | Region code                                                                               | Name                                                                                                                           |
| `compatibleFlag`                                                   | 0      | Compatibility flags                                                                       | Name                                                                                                                           |
| `pvPfCmdMemoryState`                                               | 0      | PV power factor command memory state                                                      | Name                                                                                                                           |
| `versionFlag`                                                      | 0      | Firmware version flag                                                                     | Name                                                                                                                           |
| `protEnable`                                                       | 0      | Protection enable (custom protection settings)                                            | Name                                                                                                                           |
| `backFlowSingleCtrl`                                               | 0      | Backflow single-phase control                                                             | Name                                                                                                                           |


**Winter mode / maintenance (from min_energy):**


| Property                | Value | Description                                           | Inference |
| ----------------------- | ----- | ----------------------------------------------------- | --------- |
| `tWinStart` / `tWinEnd` | ""    | Winter mode time window start/end (not configured)    | Name      |
| `utcTime`               | ""    | UTC timestamp (empty — using calendar object instead) | Name      |
| `mtncMode`              | 0     | Maintenance mode active (0=no)                        | Name      |
| `mtncRqst`              | 0     | Maintenance mode requested                            | Name      |
| `tMtncStrt`             | ""    | Maintenance start time                                | Name      |
| `winRequest`            | 0     | Winter mode request pending                           | Name      |
| `winMode`               | 0     | Winter mode currently active                          | Name      |
| `soc1` / `soc2`         | 0     | % — SoC for battery modules 1/2 (individual tracking) | Name      |
| `bdcMode`               | 0     | BDC combined mode                                     | Name      |


### 4.7 AFCI (Arc Fault Circuit Interrupter)


| Property                                               | Value                 | Description                | Inference                                                          |
| ------------------------------------------------------ | --------------------- | -------------------------- | ------------------------------------------------------------------ |
| `afciEnabled`                                          | 0                     | AFCI function enabled      | Name + MIN-XH manual mentions AFCI as optional feature             |
| `afciSelfCheck`                                        | 0                     | AFCI self-test mode active | Name                                                               |
| `afciReset`                                            | 0                     | AFCI reset command         | Name                                                               |
| `afciThresholdH` / `afciThresholdL` / `afciThresholdD` | 50000 / 30000 / 40000 | —                          | AFCI detection thresholds (high/low/default) — raw ADC or Hz units |
| `fftThresholdCount`                                    | 0                     | —                          | FFT sample count for AFCI arc detection algorithm (0=off)          |


---

## Key Findings & Anomalies


| Observation                                                | Likely explanation                                                                                                                     |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `bdc2Temp2: 104°C` (constant in history)                   | Raw ADC register value, not a real temperature. Field is not calibrated for this hardware revision. **Not** a thermal alarm.           |
| `bdc2FaultType: 7`, `bdc2WarnCode: 1`                      | BDC2 auxiliary subsystem status codes; may represent normal operational state rather than active fault.                                |
| `bdc2Ibat: 11.7A` (constant)                               | Internal reference current in auxiliary 12V supply chain, not a real load current.                                                     |
| `bdc1Vbat: ~722–736V`                                      | High-voltage battery pack (~700V DC bus). Normal for HV lithium systems on 3-phase inverters.                                          |
| `bmsVbat: 1.6–1.7V`                                        | Per-cell or per-module voltage from BMS, not the pack voltage. With bmsSoc=10%, implies very low remaining charge reading per segment. |
| `bmsSoc: 20%` at `onGridDischargeStopSOC: 20%`             | Battery at configured discharge cutoff when run captured; no further discharge allowed.                                                |
| `lost: true` in min_energy vs `lost: false` in device_list | Device_list reflects live communication state; min_energy snapshot may lag or be taken during brief datalogger sync gap.               |
| `batterySN: "\u0000\u0000…"`                               | Battery SN not transmitted to inverter via BMS. 16 null bytes = uninitialized string field.                                            |
| `epv2Total: 0`, `vpv2: ~0`                                 | PV string 2 is not connected or has zero panels. System uses 3 strings (PV1, PV3 active; PV2 absent).                                  |
| `timeTotal` decreasing across history records              | Counter resets per session or counts differently — value is not a monotonic uptime counter.                                            |
| `deviceType: 6` in min_detail vs `type: 7` in device_list  | Known Growatt API inconsistency; use `device_list.type` for routing decisions (route type 7 to `min_`* methods).                       |


