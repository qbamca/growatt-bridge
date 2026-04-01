# Feature Specification: Growatt Bridge API Redesign

**Feature Branch**: `001-api-redesign`  
**Created**: 2026-03-31  
**Status**: Draft  
**Input**: User description: "i want to redesign current API from scratch using my current experience. There will be a specific number of endpoints that i want to test and define one by one. The whole service is a facade for another API. I want to make it easier to work with, well documented and strictly controlled. Not all method and function are allowed."

## Clarifications

### Session 2026-03-31

- Q: Should endpoint tests run against the real Growatt API, a mock/stub, or both? → A: Real Growatt API only — tests hit the live upstream for every run.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover available endpoints (Priority: P1)

A developer integrating with the bridge needs to understand exactly which operations are available. They visit the API documentation and find a complete, up-to-date list of all supported endpoints with their contracts, constraints, and examples — without needing to read source code.

**Why this priority**: The explicit, bounded endpoint surface is the central design goal of this redesign. All other stories depend on knowing what endpoints exist.

**Independent Test**: Can be fully tested by loading the auto-generated API docs and verifying every permitted endpoint is listed with its request/response schema, constraints, and at least one example.

**Acceptance Scenarios**:

1. **Given** the bridge is running, **When** a developer opens the API documentation URL, **Then** they see the complete list of all allowed endpoints with schemas and descriptions — no undocumented endpoints exist.
2. **Given** a developer calls an endpoint not in the allowed list, **When** the request reaches the bridge, **Then** the bridge returns a clear 404 or 405 with a message indicating the operation is not supported.

---

### User Story 2 - Read inverter telemetry (Priority: P2)

A developer or automation consumer sends a request to the bridge to retrieve live power output and energy statistics for a specific device. The bridge returns a normalized, consistently shaped response — regardless of the Growatt device family (MIN vs SPH).

**Why this priority**: Telemetry reading is the most frequent use case and must work reliably before write operations are considered.

**Independent Test**: Can be fully tested by calling the telemetry endpoint for a known device serial number and asserting the response contains expected normalized fields and correct HTTP status.

**Acceptance Scenarios**:

1. **Given** a valid device serial number, **When** a GET telemetry request is made, **Then** the response contains normalized power/energy fields with consistent field names across device families.
2. **Given** an unknown device serial number, **When** a GET telemetry request is made, **Then** the bridge returns 404 with a descriptive error message.
3. **Given** the upstream Growatt API is unreachable, **When** a telemetry request is made, **Then** the bridge returns 502 with a clear upstream error description.

---

### User Story 3 - Execute a permitted write command (Priority: P3)

An automation consumer sends a POST request to change an inverter setting (e.g. charge time window). The bridge validates the request against the explicit allowlist of permitted operations and parameter constraints, then forwards it to Growatt and returns a structured success/failure response.

**Why this priority**: Write operations carry risk; they must only be permitted after the read surface is stable and the safety contract is clearly defined.

**Independent Test**: Can be fully tested by calling a write endpoint with valid parameters and verifying the response, then calling with out-of-range parameters and verifying rejection — all without touching a real inverter (dry-run / mock mode).

**Acceptance Scenarios**:

1. **Given** write mode is enabled and an operation is on the allowlist, **When** a POST is made with valid parameters, **Then** the bridge executes the operation and returns a success result.
2. **Given** write mode is enabled, **When** a POST is made with parameters outside defined safe ranges, **Then** the bridge rejects the request with 422 and lists the validation errors.
3. **Given** write mode is disabled (readonly), **When** any POST write command is sent, **Then** the bridge returns 403 with a message indicating readonly mode is active.
4. **Given** an operation not on the allowlist, **When** a POST is made, **Then** the bridge returns 404 listing which operations are permitted.

---

### User Story 4 - Dry-run validate before writing (Priority: P3)

A developer wants to verify their payload is correct before making a real change. They call a validate endpoint that checks all constraints (allowlist, parameter ranges, device family compatibility) without touching the inverter.

**Why this priority**: Safety validation without side effects reduces integration errors and is required for confident write adoption.

**Independent Test**: Can be fully tested independently — calls validate endpoint with both valid and invalid payloads, asserts response shape and validation errors without any real device interaction.

**Acceptance Scenarios**:

1. **Given** a valid payload for an allowlisted operation, **When** the validate endpoint is called, **Then** the response indicates `valid=true` with no errors.
2. **Given** an invalid payload (wrong type or out-of-range value), **When** the validate endpoint is called, **Then** the response indicates `valid=false` with a list of specific field-level errors.

---

### Edge Cases

- What happens when the Growatt upstream returns an unexpected response shape? Bridge must not expose raw upstream errors — it must normalize them into the standard error shape.
- How does the bridge behave when a device serial belongs to a plant not covered by the configured API token? Return 404 with a clear scope message.
- What happens if the same write operation is called at a rate exceeding safe limits? Return 429 with retry-after guidance.
- What happens when a device family is detected as UNKNOWN? Endpoint must return an explicit unsupported response rather than a silent failure.
- What if the bridge is misconfigured (missing API token)? Startup must fail with a clear configuration error, not a runtime 500.

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
- **FR-010**: The bridge MUST enforce a per-device write rate limit and return 429 with retry guidance when exceeded.
- **FR-011**: The bridge MUST expose a health endpoint that reports service liveness and readiness to connect to Growatt Cloud.
- **FR-012**: The endpoint set MUST be defined and approved one at a time before implementation; each endpoint MUST have a passing test suite — executed against the real Growatt API — before the next endpoint is added.

### Key Entities *(include if feature involves data)*

- **Plant**: A solar installation registered in Growatt Cloud, identified by `plant_id`. Contains one or more devices.
- **Device**: An inverter registered under a plant, identified by `device_sn`. Has a detected family (MIN, SPH, or UNKNOWN) that determines available operations.
- **Operation**: A named write action (e.g., set-charge-time-segment). Must be on the allowlist; has per-family parameter schemas and safe-range constraints.
- **Command Request**: The payload for a write operation — operation name plus parameters map.
- **Command Response**: The result of a write — success flag, operation name, device SN, and optional detail.
- **Audit Entry**: An immutable record of a write attempt — timestamp, device SN, operation, parameters, and result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer new to the bridge can discover all available endpoints and their full contracts without reading source code, within 5 minutes of the service starting.
- **SC-002**: Every endpoint returns a response conforming to its documented schema 100% of the time for valid inputs.
- **SC-003**: Invalid write requests (out-of-range parameters, non-allowlisted operations) are rejected before reaching Growatt Cloud in 100% of cases.
- **SC-004**: Each defined endpoint has full test coverage of its documented acceptance scenarios before the next endpoint enters development.
- **SC-005**: The total number of accessible bridge endpoints exactly matches the explicitly approved endpoint list — verified by an automated surface-area test.
- **SC-006**: Write rate limiting prevents exceeding the configured maximum write operations per device per time window in 100% of cases.

## Assumptions

- The upstream is Growatt OpenAPI V1; the redesign changes the bridge's external surface, not the upstream integration mechanism.
- The new endpoint set will be a strict subset of what the current bridge exposes — no new upstream Growatt capabilities are introduced in this redesign.
- API consumers are automation clients or developers on a local/internal network; public internet exposure and caller authentication are out of scope.
- Endpoints will be authored and approved one by one; this spec will be updated as each endpoint is finalized.
- Device family auto-detection (MIN vs SPH) is retained from the current implementation; callers will not need to specify family.
- Readonly mode (no writes) is the default; write mode requires explicit opt-in via environment configuration.
