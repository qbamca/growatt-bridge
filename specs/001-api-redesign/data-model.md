# Data Model: 001-api-redesign

Logical entities for the bridge API and persistence boundaries. Implementation uses Pydantic models in code; this document is the conceptual contract.

## Plant

| Field | Type | Notes |
|-------|------|--------|
| `plant_id` | string | Growatt plant identifier; from env `GROWATT_PLANT_ID` for MVP (single plant). |

**Relationships**: Has one or more **Devices** in Growatt Cloud; MVP configures one plant.

---

## Device

| Field | Type | Notes |
|-------|------|--------|
| `device_sn` | string | Serial number; from `GROWATT_DEVICE_SN`; must match `{device_sn}` path param (FR-020). |
| `family` | enum-like string | `MIN`, `SPH`, or `UNKNOWN` — drives normalization and supported ops. |

**Validation**: Unknown SN → **404**. UNKNOWN family → explicit unsupported response where required by spec edge cases.

**Relationships**: Belongs to a **Plant**; subject of parameters, telemetry, history, and writes.

---

## Operation (write allowlist)

| Field | Type | Notes |
|-------|------|--------|
| `operation_id` | string | Stable ID (e.g. allowlist key). |
| `parameter_schema` | map | Per-family constraints (FR-004, FR-006). |

**Rules**: Not on allowlist → **404** listing permitted ops (FR-006). Readonly mode → **403** on any write (FR-005).

---

## Command request

| Field | Type | Notes |
|-------|------|--------|
| `operation` | string | Must be allowlisted. |
| `parameters` | object | Key-value payload; validated before upstream (FR-004). |
| `device_sn` | string | From path; must match configured device list. |

---

## Command response

| Field | Type | Notes |
|-------|------|--------|
| `success` | boolean | Outcome of bridge + upstream execution. |
| `operation` | string | Echo operation id. |
| `device_sn` | string | Echo. |
| `detail` | optional string/object | Bridge-defined summary. |
| `readback` | optional object | Present when `BRIDGE_REQUIRE_READBACK=true`: contains `changed_fields`: `{ "field": { "before": …, "after": … } }` for changed fields only. |

---

## Audit entry (append-only JSONL)

Immutable record per write attempt (FR-009).

| Field | Type | Notes |
|-------|------|--------|
| `timestamp` | string (UTC ISO 8601) | When the attempt was processed. |
| `device_sn` | string | Target device. |
| `operation` | string | Operation id. |
| `parameters` | object | Redact secrets if ever introduced. |
| `result` | string or object | Success/failure summary; no raw upstream payload. |

---

## Device parameters (CAP-01)

Normalized map of configuration keys → values. Family-specific upstream names collapsed to **canonical** bridge field names (FR-003, FR-013). Exact field set **TBD per empirical contract** (FR-016).

---

## Telemetry snapshot (CAP-03)

Point-in-time normalized fields: PV, grid, battery (SOC etc. when present), load, etc. Battery fields **omitted** when device has no battery (FR-014). Exact schema **TBD per empirical contract** (FR-016).

---

## Historical record (CAP-04)

Time-bucketed energy rows (daily / monthly minimum). Empty list when no data (FR-015). Bucket labeling vs UTC **TBD per empirical contract** (FR-016, FR-025).

---

## Error envelope (API)

Cross-cutting type for **4xx/5xx/429** responses (FR-008). Includes machine-readable `code`, human message, optional `details`, and for rate limit **`retry_after_seconds`** aligned with `Retry-After` header. See `contracts/error-envelope.schema.json`.

---

## State transitions (session)

Not entity CRUD — **Shine session**: unauthenticated → authenticated (cookies + JWT scheduling) → proactive refresh before `exp` → on failure, reactive re-auth once → terminal error to caller if retry fails (FR-017).
