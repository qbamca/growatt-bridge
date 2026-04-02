# Feature Specification: Growatt Bridge API Redesign

**Feature Branch**: `001-api-redesign`  
**Created**: 2026-03-31  
**Status**: Draft  
**Input**: User description: "i want to redesign current API from scratch using my current experience. There will be a specific number of endpoints that i want to test and define one by one. The whole service is a facade for another API. I want to make it easier to work with, well documented and strictly controlled. Not all method and function are allowed."

## Capability Inventory

The following capabilities define the complete scope of the API surface. Each capability will be specified in detail empirically — one at a time, based on real data from the upstream Growatt API.

| # | Capability | Category | Status |
|---|------------|----------|--------|
| CAP-01 | Read inverter parameters | Configuration read | To be detailed |
| CAP-02 | Write inverter parameters | Configuration write | To be detailed |
| CAP-03 | Current telemetry (incl. battery SOC where present) | Live data read | To be detailed |
| CAP-04 | Historical energy data | Historical data read | To be detailed |

**Note**: Details for each capability (exact fields, request/response shape, constraints) will be added to this spec iteratively as empirical data from the live Growatt API is collected.

---

## Clarifications

### Session 2026-03-31

- Q: Should endpoint tests run against the real Growatt API, a mock/stub, or both? → A: Real Growatt API only — tests hit the live upstream for every run.
- Q: Does the caller need to provide plant ID or device SN in requests, or does the bridge resolve them internally? → A: Plant ID and device SN are configured statically via environment variables; the bridge uses them for all upstream calls. The API exposes a `GET /devices` discovery endpoint that echoes the configured device(s) so callers can be self-orienting. The `{device_sn}` path parameter is validated against the configured value — unknown SNs return 404.
- Q: Which upstream auth mechanism is used? → A: The Growatt OpenAPI V1 token approach is removed entirely. All upstream calls — reads and writes — go through the Shine web portal session (username + password via `newTwoLoginAPI.do`). The session is reused across requests and re-established reactively on auth failure (FR-017).

### Session 2026-04-02

- Q: What is the scope of the rate limit — per-device writes only (FR-010) or global? → A: Global per-user limit covering both read and write requests. Exact threshold is TBD; the safer/lower value must be chosen. The env var `BRIDGE_RATE_LIMIT` controls the limit and must default to a conservative value.
- Q: What URL versioning strategy should the redesigned API use? → A: Header-based versioning — no URL prefix (endpoints remain at root); version is communicated via request/response headers. Specific header name (e.g. `Accept` media-type or custom `API-Version`) to be decided during planning.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover available endpoints (Priority: P1)

A developer integrating with the bridge needs to understand exactly which operations are available. They visit the API documentation and find a complete, up-to-date list of all supported endpoints with their contracts, constraints, and examples — without needing to read source code.

**Why this priority**: The explicit, bounded endpoint surface is the central design goal of this redesign. All other stories depend on knowing what endpoints exist.

**Independent Test**: Can be fully tested by loading the auto-generated API docs and verifying every permitted endpoint is listed with its request/response schema, constraints, and at least one example.

**Acceptance Scenarios**:

1. **Given** the bridge is running, **When** a developer opens the API documentation URL, **Then** they see the complete list of all allowed endpoints with schemas and descriptions — no undocumented endpoints exist.
2. **Given** a developer calls an endpoint not in the allowed list, **When** the request reaches the bridge, **Then** the bridge returns a clear 404 or 405 with a message indicating the operation is not supported.

---

### User Story 2 - Discover available devices (Priority: P1)

An automation consumer or developer calls the bridge to find out which devices are available before making any device-specific requests. The bridge returns the list of configured devices with their serial numbers and detected families.

**Why this priority**: Callers need to know valid device SNs before calling any device-scoped endpoint. This endpoint makes the API self-orienting without requiring out-of-band configuration knowledge.

**Independent Test**: Can be fully tested by calling `GET /devices` and asserting the response contains at least one device entry with a serial number and family field.

**Acceptance Scenarios**:

1. **Given** the bridge is running with a configured device SN, **When** `GET /devices` is called, **Then** the response contains the configured device(s) with serial number and detected family.
2. **Given** a caller uses a device SN returned by `GET /devices`, **When** they call any device-scoped endpoint, **Then** the request is accepted.
3. **Given** a caller uses a device SN not in the `GET /devices` response, **When** they call any device-scoped endpoint, **Then** the bridge returns 404.

---

### User Story 4 - Read inverter telemetry (Priority: P2)

A developer or automation consumer sends a request to the bridge to retrieve live power output and energy statistics for a specific device, including battery SOC where the device has a battery. The bridge returns a normalized, consistently shaped response — regardless of the Growatt device family (MIN vs SPH). Battery-related fields are included when present and omitted when the device has no battery.

**Why this priority**: Telemetry reading is the most frequent use case and must work reliably before write operations are considered.

**Independent Test**: Can be fully tested by calling the telemetry endpoint for a known device serial number and asserting the response contains expected normalized fields and correct HTTP status.

**Acceptance Scenarios**:

1. **Given** a valid device serial number, **When** a GET telemetry request is made, **Then** the response contains normalized power/energy fields with consistent field names across device families.
2. **Given** an unknown device serial number, **When** a GET telemetry request is made, **Then** the bridge returns 404 with a descriptive error message.
3. **Given** the upstream Growatt API is unreachable, **When** a telemetry request is made, **Then** the bridge returns 502 with a clear upstream error description.

---

### User Story 5 - Execute a permitted write command (Priority: P3)

An automation consumer sends a POST request to change an inverter setting (e.g. charge time window). The bridge validates the request against the explicit allowlist of permitted operations and parameter constraints, then forwards it to Growatt and returns a structured success/failure response.

**Why this priority**: Write operations carry risk; they must only be permitted after the read surface is stable and the safety contract is clearly defined.

**Independent Test**: Can be fully tested by calling a write endpoint with valid parameters and verifying the response, then calling with out-of-range parameters and verifying rejection — all without touching a real inverter (dry-run / mock mode).

**Acceptance Scenarios**:

1. **Given** write mode is enabled and an operation is on the allowlist, **When** a POST is made with valid parameters, **Then** the bridge executes the operation and returns a success result.
2. **Given** write mode is enabled, **When** a POST is made with parameters outside defined safe ranges, **Then** the bridge rejects the request with 422 and lists the validation errors.
3. **Given** write mode is disabled (readonly), **When** any POST write command is sent, **Then** the bridge returns 403 with a message indicating readonly mode is active.
4. **Given** an operation not on the allowlist, **When** a POST is made, **Then** the bridge returns 404 listing which operations are permitted.

---

### User Story 6 - Dry-run validate before writing (Priority: P3)

A developer wants to verify their payload is correct before making a real change. They call a validate endpoint that checks all constraints (allowlist, parameter ranges, device family compatibility) without touching the inverter.

**Why this priority**: Safety validation without side effects reduces integration errors and is required for confident write adoption.

**Independent Test**: Can be fully tested independently — calls validate endpoint with both valid and invalid payloads, asserts response shape and validation errors without any real device interaction.

**Acceptance Scenarios**:

1. **Given** a valid payload for an allowlisted operation, **When** the validate endpoint is called, **Then** the response indicates `valid=true` with no errors.
2. **Given** an invalid payload (wrong type or out-of-range value), **When** the validate endpoint is called, **Then** the response indicates `valid=false` with a list of specific field-level errors.

---

### User Story 7 - Read inverter parameters (Priority: P2)

A developer or automation consumer sends a request to retrieve the current configuration settings of a specific inverter (e.g. charge time windows, charge current limits, work mode). The bridge returns a normalized, consistently shaped response with the current parameter values.

**Why this priority**: Reading current parameters is a prerequisite for safe write operations — callers need to know the current state before changing it. It is also a lower-risk operation than writing.

**Independent Test**: Can be fully tested by calling the read-parameters endpoint for a known device serial number and asserting the response contains expected normalized configuration fields.

**Acceptance Scenarios**:

1. **Given** a valid device serial number, **When** a GET parameters request is made, **Then** the response contains normalized configuration fields with consistent names across device families.
2. **Given** an unknown device serial number, **When** a GET parameters request is made, **Then** the bridge returns 404 with a descriptive error message.
3. **Given** the upstream Growatt API is unreachable, **When** a parameters request is made, **Then** the bridge returns 502 with a clear upstream error description.

---

### User Story 8 - Read historical energy data (Priority: P3)

A developer or reporting consumer sends a request to retrieve past energy production and consumption totals for a specific device over a defined time range (daily, monthly, or yearly granularity). The bridge returns a normalized list of time-bucketed energy records.

**Why this priority**: Historical data is useful for reporting and dashboards but is not required for live monitoring or control — it can be added after live-data endpoints are stable.

**Independent Test**: Can be fully tested by calling the historical data endpoint with a known device serial and date range, asserting the response contains a list of records with consistent time-bucket and energy fields.

**Acceptance Scenarios**:

1. **Given** a valid device serial number and a date range, **When** a GET historical data request is made with daily granularity, **Then** the response contains one normalized record per calendar day with energy totals.
2. **Given** a valid device serial number, **When** a GET historical data request is made with monthly granularity, **Then** the response contains one normalized record per calendar month.
3. **Given** a date range with no recorded data, **When** a GET historical data request is made, **Then** the bridge returns an empty list (not an error).
4. **Given** an unknown device serial number, **When** a GET historical data request is made, **Then** the bridge returns 404.

---

### Edge Cases

- What happens when the Growatt upstream returns an unexpected response shape? Bridge must not expose raw upstream errors — it must normalize them into the standard error shape.
- How does the bridge behave when a device serial belongs to a plant not covered by the configured API token? Return 404 with a clear scope message.
- What if a caller exceeds the global request rate limit (reads or writes)? Return 429 with `Retry-After` guidance.
- What happens when a device family is detected as UNKNOWN? Endpoint must return an explicit unsupported response rather than a silent failure.
- What if the bridge is misconfigured (missing API token)? Startup must fail with a clear configuration error, not a runtime 500.
- What if the Shine web session expires mid-operation despite proactive refresh? The reactive fallback must detect the auth failure, log a WARNING, re-authenticate once, and retry — if the retry also fails, return a clear error to the caller with no further retries.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The bridge MUST expose only an explicitly defined, fixed set of endpoints — no other Growatt API surface is accessible through the bridge.
- **FR-002**: Every permitted endpoint MUST have a documented request schema, response schema, and error contract visible in the auto-generated API documentation.
- **FR-003**: All read endpoints MUST return normalized response shapes consistent across Growatt device families (MIN/TLX, SPH/MIX) — callers MUST NOT need to handle family-specific field names.
- **FR-004**: All write endpoints MUST validate parameters against defined safe ranges before forwarding to Growatt Cloud; out-of-range requests MUST be rejected with field-level error detail.
- **FR-005**: The bridge MUST support a readonly mode that blocks all write endpoints at the application level, returning 403 for any write attempt.
- **FR-006**: The bridge MUST maintain an explicit write allowlist; write operations not on the allowlist MUST return 404 even in write-enabled mode.
- **FR-007**: Each write endpoint MUST have a corresponding dry-run validate endpoint that exercises all validation checks without making upstream changes.
- **FR-008**: The bridge MUST return a structured error response (consistent shape) for all error conditions — no raw upstream error messages exposed to callers.
- **FR-009**: The bridge MUST log each write attempt (success or failure) in an append-only audit trail.
- **FR-010**: The bridge MUST enforce a global per-user rate limit covering both read and write requests; any request from a given caller exceeding the configured threshold MUST return 429 with `Retry-After` guidance. The exact limit value is TBD and MUST be configurable via `BRIDGE_RATE_LIMIT`; the default MUST be a conservative (low) value.
- **FR-011**: The bridge MUST expose a health endpoint that reports service liveness and readiness to connect to Growatt Cloud.
- **FR-012**: The endpoint set MUST be defined and approved one at a time before implementation; each endpoint MUST have a passing test suite — executed against the real Growatt API — before the next endpoint is added.
- **FR-013**: The bridge MUST expose a read-parameters endpoint (CAP-01) that returns the current inverter configuration settings in a normalized shape consistent across device families.
- **FR-014**: The bridge MUST expose a current-telemetry endpoint (CAP-03) that returns live power flow data in a normalized shape consistent across device families; battery SOC and state fields MUST be included when the device has a battery and omitted when it does not.
- **FR-015**: The bridge MUST expose a historical-data endpoint (CAP-04) supporting at minimum daily and monthly granularity; it MUST return an empty list (not an error) when no data exists for the requested range.
- **FR-016**: The specific fields, constraints, and request/response shapes for each capability (CAP-01 through CAP-04) MUST be defined empirically from live Growatt API data before the corresponding endpoint is implemented.
- **FR-017**: The bridge MUST manage the Shine web session using a two-layer strategy: (1) **proactive** — decode the `exp` claim from `cpowerAuth` on login and re-authenticate before expiry so no request ever hits an expired session under normal conditions; (2) **reactive fallback** — if an upstream response signals an invalid session despite proactive refresh (redirect to login or `success: false` auth body), re-authenticate once and retry; if the retry also fails, return a clear error to the caller. Every reactive re-auth event MUST be logged at WARNING level with the triggering URL and response status to support future diagnosis.
- **FR-018**: If login fails (`back.success` is `false`), the bridge MUST log an ERROR with the numeric code from `back.msg` and the human-readable reason from `back.error`, then halt startup — a bridge that cannot authenticate has no valid operating state.
- **FR-019**: The bridge MUST expose a `GET /devices` endpoint that returns the list of configured devices with their serial numbers and detected families; no upstream discovery call is made — the response reflects the static configuration.
- **FR-020**: All device-scoped endpoints MUST validate the `{device_sn}` path parameter against the configured device list and return 404 for any SN not in that list.

### Key Entities *(include if feature involves data)*

- **Plant**: A solar installation registered in Growatt Cloud, identified by `plant_id`. Contains one or more devices.
- **Device**: An inverter registered under a plant, identified by `device_sn`. Has a detected family (MIN, SPH, or UNKNOWN) that determines available operations.
- **Operation**: A named write action (e.g., set-charge-time-segment). Must be on the allowlist; has per-family parameter schemas and safe-range constraints.
- **Command Request**: The payload for a write operation — operation name plus parameters map.
- **Command Response**: The result of a write — success flag, operation name, device SN, and optional detail.
- **Audit Entry**: An immutable record of a write attempt — timestamp, device SN, operation, parameters, and result.
- **Device Parameters**: The current configuration settings of an inverter (e.g. charge time windows, work mode, charge current limits). Read via CAP-01, written via CAP-02.
- **Telemetry Snapshot**: A point-in-time reading of live power flow data (PV generation, grid import/export, battery charge/discharge, load, and battery SOC where present). Returned by CAP-03.
- **Historical Record**: A time-bucketed energy summary (daily or monthly totals) for a device. Returned by CAP-04.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer new to the bridge can discover all available endpoints and their full contracts without reading source code, within 5 minutes of the service starting.
- **SC-002**: Every endpoint returns a response conforming to its documented schema 100% of the time for valid inputs.
- **SC-003**: Invalid write requests (out-of-range parameters, non-allowlisted operations) are rejected before reaching Growatt Cloud in 100% of cases.
- **SC-004**: Each defined endpoint has full test coverage of its documented acceptance scenarios before the next endpoint enters development.
- **SC-005**: The total number of accessible bridge endpoints exactly matches the explicitly approved endpoint list — verified by an automated surface-area test.
- **SC-006**: The global per-user rate limit prevents any caller from exceeding the configured request threshold (reads + writes combined) in 100% of cases; excess requests receive 429 with `Retry-After`.
- **SC-007**: All four capabilities (CAP-01 through CAP-04) have defined, empirically-validated endpoint contracts before any capability enters implementation.
- **SC-008**: The telemetry endpoint (CAP-03) correctly includes battery fields for battery-equipped devices and omits them for non-battery devices.

## Upstream API Contracts

Empirically captured request/response contracts from the live Growatt server. Each entry is based on a real probe run and serves as the source of truth for implementation.

---

### Authentication — `POST /newTwoLoginAPI.do`

**Source**: probe run 2026-04-02, `audit/explore/20260402_192218_login.json`

#### Request

```
POST https://server.growatt.com/newTwoLoginAPI.do
Content-Type: application/x-www-form-urlencoded
```

| Field | Type | Description |
|-------|------|-------------|
| `userName` | string | Growatt account username |
| `password` | string | Password hashed with MD5 via `growattServer.hash_password()` — never sent in plain text |

#### Response

HTTP status is **always `200`** regardless of whether login succeeded or failed. Success is determined exclusively by `back.success`.

The top-level key is `back`. All useful data is nested under it.

**Success:**

```json
{
  "back": {
    "success": true,
    "msg": "",
    "data": [
      { "plantId": "10581915", "plantName": "Dom" }
    ],
    "deviceCount": "7",
    "user": {
      "id": 3648131,
      "accountName": "qbamca",
      "area": "Europe",
      "counrty": "Poland",
      "timeZone": 8,
      "serverUrl": "",
      "rightlevel": 1,
      "enabled": true,
      "cpowerAuth": "<JWT>",
      ...
    }
  }
}
```

**Failure (wrong username or password):**

```json
{
  "back": {
    "success": false,
    "msg": "501",
    "error": "User Does Not Exist"
  }
}
```

- `back.msg` contains a **numeric error code string** (`"501"`), not a human-readable message
- `back.error` contains the **human-readable reason** — this is the field to log and surface
- Cookies (`JSESSIONID`, `SERVERID`, `SERVERCORSID`) are still set on failure — these are unauthenticated sessions and MUST be discarded

**Fields used by the bridge:**

| Field | Notes |
|-------|-------|
| `back.success` | `true` = login accepted; `false` = credentials rejected |
| `back.msg` | Numeric error code string when `success` is `false` (e.g. `"501"`). Empty string on success. |
| `back.error` | Human-readable error reason when `success` is `false` (e.g. `"User Does Not Exist"`). Absent on success. |
| `back.data[].plantId` | Plant IDs accessible by this account |
| `back.user.serverUrl` | Regional server override — if non-empty, subsequent calls must use this URL instead of `server.growatt.com`. Observed empty for EU accounts. |
| `back.user.timeZone` | Server-side timezone offset (observed: `8` = UTC+8). Timestamps in responses are in this timezone. |
| `back.user.cpowerAuth` | JWT whose `exp` claim gives the session expiry time. Decoded on login to schedule proactive re-authentication before the session expires. |

**Fields intentionally ignored:**

| Field | Reason |
|-------|--------|
| `back.deviceCount` | Counts all device types (loggers, meters, inverters) — not useful for inverter enumeration |
| `back.user.token` | Redacted in saved response. Unused — session auth relies on cookies, not this token. |

#### Session Cookies

Three cookies are set on login and must be carried on all subsequent requests:

| Cookie | Description |
|--------|-------------|
| `JSESSIONID` | Tomcat session identifier. Primary session token. |
| `SERVERID` | Load balancer affinity — pins all requests to the same backend node. |
| `SERVERCORSID` | Same value as `SERVERID`, set with `SameSite=None` for cross-origin contexts. |

No `Max-Age` or `Expires` is set on any cookie — all are session cookies. The `cpowerAuth` JWT `exp` claim (observed TTL: **1 hour**) is used as a proxy for session lifetime.

#### Session Management

The bridge uses a two-layer session strategy:

1. **Proactive re-auth (primary)**: On login, the `exp` claim is decoded from `cpowerAuth`. The bridge schedules re-authentication before that deadline — refreshing the session and all three cookies before any request fails due to expiry.

2. **Reactive re-auth (fallback)**: If an upstream response indicates an expired or rejected session (redirect to login page, or `success: false` with an auth-related message) despite proactive refresh, the bridge re-authenticates once and retries the original request. If the retry also fails, the error is returned to the caller.

3. **Logging**: Any reactive re-auth event MUST be logged at `WARNING` level with the triggering response status and URL. This creates an observable record for diagnosing cases where the proactive strategy proves insufficient (e.g. server-side session invalidation, TTL shorter than expected). See FR-017.

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GROWATT_WEB_USERNAME` | Shine web portal username. Used for all upstream calls (reads and writes). |
| `GROWATT_WEB_PASSWORD` | Shine web portal password (plain text; hashed before sending). Used for all upstream calls. |
| `GROWATT_DEVICE_SN` | Device serial number. Used to scope all device endpoints and validate `{device_sn}` path parameters. |
| `GROWATT_PLANT_ID` | Plant ID. Used internally for device family detection and write context cookies. |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GROWATT_WEB_BASE_URL` | `https://server.growatt.com/` | Shine web portal base URL. |
| `BRIDGE_PORT` | `8081` | HTTP listen port. |
| `BRIDGE_HOST` | `0.0.0.0` | HTTP bind address. |
| `BRIDGE_READONLY` | `true` | When `true`, all write endpoints return 403. Must be set to `false` to enable writes. |
| `BRIDGE_WRITE_ALLOWLIST` | *(empty)* | Comma-separated list of permitted write operation IDs. Empty means no writes even if `BRIDGE_READONLY=false`. |
| `BRIDGE_RATE_LIMIT` | TBD (conservative) | Maximum requests (reads + writes) permitted per minute per caller. Default must be a conservative low value; exact threshold TBD. (Formerly `BRIDGE_RATE_LIMIT_WRITES`, which covered writes only.) |
| `BRIDGE_REQUIRE_READBACK` | `true` | Re-reads device config after every write and includes the diff in the response. |
| `BRIDGE_AUDIT_LOG` | `/var/log/growatt-bridge/audit.jsonl` | Path for the append-only JSONL write audit log. |

## Assumptions

- The Growatt OpenAPI V1 token approach is removed entirely; the bridge uses only the Shine web portal session (username/password) for all upstream communication.
- The new endpoint set will be a strict subset of what the current bridge exposes — no new upstream Growatt capabilities are introduced in this redesign.
- API consumers are automation clients or developers on a local/internal network; public internet exposure and caller authentication are out of scope.
- Endpoints will be authored and approved one by one; this spec will be updated as each endpoint is finalized.
- Device family auto-detection (MIN vs SPH) is retained from the current implementation; callers will not need to specify family.
- Readonly mode (no writes) is the default; write mode requires explicit opt-in via environment configuration.
- Plant ID and device SN are provided via environment configuration; the bridge does not discover them at runtime. A single plant and single device is the current target deployment.
- `GET /devices` echoes the static configuration — it does not call the upstream Growatt API.
- API versioning is header-based; no URL prefix (e.g. `/v1/`) is used. All endpoints are served at the root path. The specific version header mechanism (media-type `Accept` vs. custom `API-Version` header) will be decided during implementation planning.
