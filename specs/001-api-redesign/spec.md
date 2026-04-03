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

- Q: What is the scope of the rate limit — per-device writes only (FR-010) or global? → A: Global limit covering **upstream** read and write traffic to Growatt (not write-only). `BRIDGE_RATE_LIMIT` default **20** per rolling 60s (Session 2026-04-04). **Refined Session 2026-04-03:** no HTTP-ingress rate limiter for MVP; outbound Growatt budget only; single global upstream bucket for MVP, per-credential buckets later.
- Q: What URL versioning strategy should the redesigned API use? → A: Header-based versioning — no URL prefix (endpoints remain at root); version via **`Accept`** / **`Content-Type`** using a versioned vendor media type (refined Session 2026-04-04; see FR-021).
- Q: What shape should the `BRIDGE_REQUIRE_READBACK` diff take in the write response? → A: A `readback` object with `changed_fields` map — each key is a field name with `before`/`after` values showing only the fields that changed. Primary purpose is confirming the write actually took effect. Omitted from response when `BRIDGE_REQUIRE_READBACK=false`.

### Session 2026-04-03

- Q: How should rate limiting apply (HTTP ingress vs upstream Growatt), and how should buckets be partitioned for MVP? → A: **No incoming HTTP request rate limiter for MVP** — deployment is local, one service, one client; ingress throttling is unnecessary. The **important** limit is **outbound requests to Growatt**; use **one global upstream limiter** for MVP. **Evolution:** separate upstream limiters **per Growatt account / credential set** when multiple users are supported. `BRIDGE_RATE_LIMIT` configures the upstream (Growatt) budget.
- Q: Should the bridge HTTP listener use TLS, and what deployment context is assumed? → A: **Plain HTTP is sufficient for MVP.** The bridge runs **in Docker Compose alongside the consumer** on a private Docker network; **TLS** and **caller authentication** remain **out of scope** for MVP (operators add edge TLS if the stack is exposed beyond the compose network).
- Q: How should concurrent inbound bridge requests interact with upstream Growatt calls? → A: **Strict serialization** — **at most one outbound Growatt HTTP request in flight at a time** (global queue for all upstream traffic). Inbound requests may arrive concurrently; work waits for the queue (FR-022).
- Q: Should MVP expose Prometheus (or similar) metrics? → A: **No** — **logs + append-only audit JSONL** only for MVP; no `/metrics` scrape endpoint required (FR-023).
- Q: Should writes be idempotent (dedupe duplicate POSTs / idempotency keys)? → A: **No idempotency in MVP** — each accepted write may perform a distinct upstream action; callers avoid blind retries (FR-024).
- Q: How should normalized date/time values appear in API JSON (timezone / calendar rules)? → A: **UTC instants** — **ISO 8601** in responses unless a capability’s empirical contract defines local-calendar bucketing (FR-025).

### Session 2026-04-04

- Q: How should `BRIDGE_RATE_LIMIT` count outbound Growatt requests over time? → A: **Sliding window** — `BRIDGE_RATE_LIMIT` is the maximum number of outbound Growatt requests allowed in any rolling **60-second** period (single global bucket for MVP).
- Q: What default numeric value should `BRIDGE_RATE_LIMIT` use? → A: **20** — max outbound Growatt requests per rolling **60-second** window unless overridden via env.
- Q: How should clients send/receive API version (header-based, no URL prefix)? → A: **`Accept`** request header with a **versioned vendor media type** (e.g. `application/vnd.growatt-bridge.v1+json`); responses use a matching **`Content-Type`**.
- Q: Should health/readiness checks count toward `BRIDGE_RATE_LIMIT`? → A: **Yes** — **all** outbound HTTP to Growatt count toward the limit, including traffic from **health/readiness** when those checks contact Growatt.
- Q: For HTTP **429** (upstream budget exhausted), how should retry timing be exposed? → A: **`Retry-After`** response header **and** the same value in the structured error body (e.g. **`retry_after_seconds`**) — see FR-008.

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

**Independent Test**: Can be fully tested by calling a write endpoint with valid parameters and verifying the response, then calling with out-of-range parameters and verifying rejection — using the real Growatt API per FR-012 (same strategy as other endpoint tests; validate-only flows remain non-mutating).

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
- How does the bridge behave when a device serial is not in scope for the configured plant/credentials? Return 404 with a clear scope message.
- What if inbound traffic would exceed the **upstream** Growatt request budget (global limiter on outbound calls, **sliding 60-second** window — see FR-010)? Do not call Growatt; return **429** with **`Retry-After`** header **and** matching **`retry_after_seconds`** (or equivalent) in the structured error body (FR-008). (No separate HTTP-ingress rate limit for MVP — see FR-010.) Health/readiness probes that **do** call Growatt **share** that same upstream budget — aggressive polling can starve other endpoints.
- What happens when a device family is detected as UNKNOWN? Endpoint must return an explicit unsupported response rather than a silent failure.
- What if the bridge is misconfigured (missing required credentials or plant/device env)? Startup must fail with a clear configuration error, not a runtime 500.
- What if the Shine web session expires mid-operation despite proactive refresh? The reactive fallback must detect the auth failure, log a WARNING, re-authenticate once, and retry — if the retry also fails, return a clear error to the caller with no further retries.
- What if multiple inbound HTTP requests arrive while another upstream Growatt call is in progress? Requests wait in the **global upstream serialization queue** (FR-022); they MUST NOT be rejected solely because of concurrency. Ordering is FIFO unless a later spec adds priority.
- What if a client **retries** the same write after a timeout or network error? **MVP does not dedupe** — repeated identical POSTs MAY apply the change multiple times upstream; callers MUST avoid blind retries (use validate-only flows or app-level deduplication). See **FR-024**.
- How are upstream timestamps (Growatt server/account timezone) presented to callers? Normalized **instants** use **UTC ISO 8601** per **FR-025**; local-day or calendar-bucket semantics for historical data are defined per capability when empirically captured (**FR-016**).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The bridge MUST expose only an explicitly defined, fixed set of endpoints — no other Growatt API surface is accessible through the bridge.
- **FR-002**: Every permitted endpoint MUST have a documented request schema, response schema, and error contract visible in the auto-generated API documentation, including supported **`Accept`** values for API version negotiation (FR-021).
- **FR-003**: All read endpoints MUST return normalized response shapes consistent across Growatt device families (MIN/TLX, SPH/MIX) — callers MUST NOT need to handle family-specific field names. **Instant timestamps** in normalized JSON MUST follow **FR-025**.
- **FR-004**: All write endpoints MUST validate parameters against defined safe ranges before forwarding to Growatt Cloud; out-of-range requests MUST be rejected with field-level error detail.
- **FR-005**: The bridge MUST support a readonly mode that blocks all write endpoints at the application level, returning 403 for any write attempt.
- **FR-006**: The bridge MUST maintain an explicit write allowlist; write operations not on the allowlist MUST return 404 even in write-enabled mode.
- **FR-007**: Each write endpoint MUST have a corresponding dry-run validate endpoint that exercises all validation checks without making upstream changes.
- **FR-008**: The bridge MUST return a structured error response (consistent shape) for all error conditions — no raw upstream error messages exposed to callers. For **429** responses (including upstream rate limit per FR-010), the bridge MUST send the **`Retry-After`** HTTP header **and** include the same retry interval in the structured error body (field name **`retry_after_seconds`**, integer seconds), with values consistent between header and body.
- **FR-009**: The bridge MUST log each write attempt (success or failure) in an append-only audit trail.
- **FR-010**: The bridge MUST enforce a configurable rate limit on **outbound requests to Growatt Cloud** (all upstream reads and writes **and any other Growatt HTTP traffic**, including calls made for **health/readiness** when those checks contact Growatt), using a **single global bucket** for the configured credentials in MVP. The limit MUST be enforced as a **sliding window** of **60 seconds**: `BRIDGE_RATE_LIMIT` is the maximum number of outbound Growatt requests in any rolling 60-second period. The default MUST be **20** (conservative); operators MAY raise it via environment configuration. When satisfying an inbound bridge request would exceed that upstream budget, the bridge MUST NOT call Growatt and MUST return **429** with `Retry-After` **and** structured body per **FR-008**. **HTTP-level rate limiting of inbound traffic to the bridge** is **not required** for MVP (local, single-client use). **Evolution:** when multiple credential sets exist, upstream limits SHOULD be tracked **per credential identity** (separate buckets).
- **FR-011**: The bridge MUST expose a health endpoint that reports service liveness and readiness to connect to Growatt Cloud. Any upstream HTTP performed to determine readiness MUST count toward **FR-010** (same sliding-window budget as all other Growatt calls).
- **FR-012**: The endpoint set MUST be defined and approved one at a time before implementation; each endpoint MUST have a passing test suite — executed against the real Growatt API — before the next endpoint is added.
- **FR-013**: The bridge MUST expose a read-parameters endpoint (CAP-01) that returns the current inverter configuration settings in a normalized shape consistent across device families.
- **FR-014**: The bridge MUST expose a current-telemetry endpoint (CAP-03) that returns live power flow data in a normalized shape consistent across device families; battery SOC and state fields MUST be included when the device has a battery and omitted when it does not.
- **FR-015**: The bridge MUST expose a historical-data endpoint (CAP-04) supporting at minimum daily and monthly granularity; it MUST return an empty list (not an error) when no data exists for the requested range.
- **FR-016**: The specific fields, constraints, and request/response shapes for each capability (CAP-01 through CAP-04) MUST be defined empirically from live Growatt API data before the corresponding endpoint is implemented.
- **FR-017**: The bridge MUST manage the Shine web session using a two-layer strategy: (1) **proactive** — decode the `exp` claim from `cpowerAuth` on login and re-authenticate before expiry so no request ever hits an expired session under normal conditions; (2) **reactive fallback** — if an upstream response signals an invalid session despite proactive refresh (redirect to login or `success: false` auth body), re-authenticate once and retry; if the retry also fails, return a clear error to the caller. Every reactive re-auth event MUST be logged at WARNING level with the triggering URL and response status to support future diagnosis.
- **FR-018**: If login fails (`back.success` is `false`), the bridge MUST log an ERROR with the numeric code from `back.msg` and the human-readable reason from `back.error`, then halt startup — a bridge that cannot authenticate has no valid operating state.
- **FR-019**: The bridge MUST expose a `GET /devices` endpoint that returns the list of configured devices with their serial numbers and detected families; no upstream discovery call is made — the response reflects the static configuration.
- **FR-020**: All device-scoped endpoints MUST validate the `{device_sn}` path parameter against the configured device list and return 404 for any SN not in that list.
- **FR-021**: The API MUST NOT use URL path segments for version (no `/v1/` prefix). Clients MUST negotiate version using the **`Accept`** header with a **versioned vendor media type** (e.g. `application/vnd.growatt-bridge.v1+json`); successful responses MUST use a matching **`Content-Type`**. The exact media type string(s) MUST appear in the auto-generated API documentation. Requests whose `Accept` does not include any supported version MUST receive **406** with the structured error shape listing supported media types.
- **FR-022**: The bridge MUST serialize **all outbound HTTP to Growatt Cloud** — **at most one upstream request in flight at a time** (global FIFO queue), including reads, writes, health/readiness traffic that contacts Growatt, and login/session refresh calls that count toward **FR-010**. Inbound HTTP requests to the bridge MAY arrive concurrently; any work that performs upstream I/O MUST pass through this queue. **FR-010** remains in force on top of serialization (sliding-window cap still applies to completed outbound requests).
- **FR-023**: For **MVP**, operational observability MUST rely on **application logging** (including WARNING/ERROR events per **FR-017** / **FR-018**) and the **append-only write audit log** (**FR-009**). A **Prometheus** `/metrics` endpoint or other metrics scrape surface is **not required**. **Evolution:** add metrics when dashboards, SLOs, or multi-tenant operations require them.
- **FR-024**: For **MVP**, the bridge MUST **not** implement write **idempotency** (no `Idempotency-Key` header, payload-hash deduplication, or cached replay of prior write outcomes). Each successful mutating request represents an intentional upstream write. **Evolution:** add idempotency when unreliable networks or multiple consumers require deduplicated side effects.
- **FR-025**: All **instant timestamps** in normalized bridge JSON (reads and write responses, including audit-relevant fields surfaced to callers) MUST use **UTC**, encoded as **ISO 8601** (e.g. `...Z` or explicit `+00:00`). The bridge MUST convert from Growatt upstream timezone data as needed. When a capability requires **local-calendar** semantics (e.g. daily/monthly energy buckets aligned to local midnight), the **empirical contract** for that endpoint (**FR-016**) MUST define bucket boundaries or date labels; such fields MAY accompany UTC instants as documented.

### Key Entities *(include if feature involves data)*

- **Plant**: A solar installation registered in Growatt Cloud, identified by `plant_id`. Contains one or more devices.
- **Device**: An inverter registered under a plant, identified by `device_sn`. Has a detected family (MIN, SPH, or UNKNOWN) that determines available operations.
- **Operation**: A named write action (e.g., set-charge-time-segment). Must be on the allowlist; has per-family parameter schemas and safe-range constraints.
- **Command Request**: The payload for a write operation — operation name plus parameters map.
- **Command Response**: The result of a write — success flag, operation name, device SN, optional detail, and an optional `readback` object. The `readback` object contains a `changed_fields` map: `{"field_name": {"before": <old_value>, "after": <new_value>}}` listing only the fields that changed after the write. It is included when `BRIDGE_REQUIRE_READBACK=true` and omitted otherwise. Its purpose is confirming the write actually took effect on the device.
- **Audit Entry**: An immutable record of a write attempt — timestamp, device SN, operation, parameters, and result.
- **Device Parameters**: The current configuration settings of an inverter (e.g. charge time windows, work mode, charge current limits). Read via CAP-01, written via CAP-02.
- **Telemetry Snapshot**: A point-in-time reading of live power flow data (PV generation, grid import/export, battery charge/discharge, load, and battery SOC where present). Returned by CAP-03.
- **Historical Record**: A time-bucketed energy summary (daily or monthly totals) for a device. Returned by CAP-04. Bucket labeling vs UTC instants follow the CAP-04 empirical contract and **FR-025**.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer new to the bridge can discover all available endpoints and their full contracts without reading source code, within 5 minutes of the service starting.
- **SC-002**: Every endpoint returns a response conforming to its documented schema 100% of the time for valid inputs.
- **SC-003**: Invalid write requests (out-of-range parameters, non-allowlisted operations) are rejected before reaching Growatt Cloud in 100% of cases.
- **SC-004**: Each defined endpoint has full test coverage of its documented acceptance scenarios before the next endpoint enters development.
- **SC-005**: The total number of accessible bridge endpoints exactly matches the explicitly approved endpoint list — verified by an automated surface-area test.
- **SC-006**: The global **upstream** (Growatt) rate limit — **sliding 60-second window**, default **20** outbound calls per window unless configured otherwise — prevents the bridge from exceeding the configured outbound request threshold (upstream reads + writes + readiness-related Growatt calls, per FR-010/FR-011) in 100% of cases; when the budget is exhausted, the bridge does not call Growatt and the HTTP client receives **429** with **`Retry-After`** and **`retry_after_seconds`** in the structured error body (FR-008).
- **SC-007**: All four capabilities (CAP-01 through CAP-04) have defined, empirically-validated endpoint contracts before any capability enters implementation.
- **SC-008**: The telemetry endpoint (CAP-03) correctly includes battery fields for battery-equipped devices and omits them for non-battery devices.
- **SC-009**: Under concurrent inbound load, the bridge never has **more than one** outbound Growatt HTTP request **in flight** at the same time — consistent with **FR-022** (verifiable via tests or concurrency instrumentation).
- **SC-010**: MVP operations do not require a Prometheus (or equivalent) metrics endpoint — **logs** and **`BRIDGE_AUDIT_LOG`** satisfy traceability and diagnosis per **FR-023**.
- **SC-011**: MVP does **not** guarantee idempotent behavior for repeated write POSTs — duplicate submissions may duplicate upstream effects; integrators rely on documented behavior per **FR-024**.
- **SC-012**: Normalized responses expose **instant** times as **UTC ISO 8601** per **FR-025**; any local-calendar bucket fields for historical data are defined in the capability contract (**FR-016**) and documented in the API spec.

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
| `BRIDGE_RATE_LIMIT` | `20` | Maximum **upstream** requests to Growatt Cloud (reads + writes) in any rolling **60-second sliding window**, **global single bucket** for MVP. Does **not** configure HTTP-ingress throttling. (Formerly `BRIDGE_RATE_LIMIT_WRITES`, which covered writes only.) |
| `BRIDGE_REQUIRE_READBACK` | `true` | Re-reads device config after every write and includes the diff in the response. |
| `BRIDGE_AUDIT_LOG` | `/var/log/growatt-bridge/audit.jsonl` | Path for the append-only JSONL write audit log. |

## Assumptions

- The Growatt OpenAPI V1 token approach is removed entirely; the bridge uses only the Shine web portal session (username/password) for all upstream communication.
- The new endpoint set will be a strict subset of what the current bridge exposes — no new upstream Growatt capabilities are introduced in this redesign.
- API consumers are automation clients or developers on a local/internal network; public internet exposure and caller authentication are out of scope. **MVP:** the bridge is deployed **in Docker Compose with the consumer** on a private Docker network; **plain HTTP** for the bridge listener is sufficient — **TLS** is not required in MVP (add reverse-proxy TLS only if exposing beyond the compose network). No mandatory rate limit on **inbound** HTTP — rate limiting targets **outbound** Growatt traffic (see FR-010).
- Endpoints will be authored and approved one by one; this spec will be updated as each endpoint is finalized.
- Device family auto-detection (MIN vs SPH) is retained from the current implementation; callers will not need to specify family.
- Readonly mode (no writes) is the default; write mode requires explicit opt-in via environment configuration.
- Plant ID and device SN are provided via environment configuration; the bridge does not discover them at runtime. A single plant and single device is the current target deployment.
- `GET /devices` echoes the static configuration — it does not call the upstream Growatt API.
- API versioning is header-based; no URL prefix (e.g. `/v1/`) is used. All endpoints are served at the root path. Version is negotiated with **`Accept`** (versioned vendor media type) and echoed in **`Content-Type`** (see FR-021).
- **MVP observability** is **application logs** plus the **append-only audit JSONL** (`BRIDGE_AUDIT_LOG`); **Prometheus `/metrics`** (or similar) is **out of scope** for MVP (**FR-023**).
- **Write idempotency** (deduplicating retries or identical POSTs) is **out of scope** for MVP (**FR-024**).
- **Normalized instants** in JSON use **UTC** (**ISO 8601**) per **FR-025**; local-calendar bucketing for historical energy is specified per capability when empirically captured (**FR-016**).
