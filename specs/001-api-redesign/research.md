# Research: 001-api-redesign

Consolidated decisions for the Growatt Bridge API redesign. All items that were candidates for "NEEDS CLARIFICATION" in Technical Context are resolved here.

---

## 1. HTTP framework and documentation

**Decision**: Keep **FastAPI** for the bridge service.

**Rationale**: Already in production in this repo; provides OpenAPI generation (FR-002), Pydantic v2 models, and aligns with team stack. Spec requires auto-generated API docs listing versioned `Accept` values (FR-002, FR-021).

**Alternatives considered**: Starlette-only (more manual OpenAPI); Flask (less native async alignment with future scaling).

---

## 2. API versioning (no URL prefix)

**Decision**: **Header-based** negotiation using a **vendor media type** in `Accept` and matching `Content-Type` on success (e.g. `application/vnd.growatt-bridge.v1+json`). Unsupported `Accept` → **406** with structured error listing supported types (FR-021).

**Rationale**: Matches clarified requirement; keeps URLs stable at root (e.g. `GET /devices`).

**Alternatives considered**: URL prefix `/v1` (rejected by spec); query parameter `?version=` (poor cache semantics, not requested).

---

## 3. Upstream authentication

**Decision**: **Shine web portal only** — `POST .../newTwoLoginAPI.do` with MD5-hashed password via `growattServer.hash_password()`, maintain **JSESSIONID**, **SERVERID**, **SERVERCORSID** cookies; proactive re-auth from `cpowerAuth` JWT `exp`; reactive re-auth on auth failure with single retry (FR-017, FR-018). Remove Growatt OpenAPI V1 token usage from the bridge’s critical path.

**Rationale**: Clarified in spec; single auth story simplifies client and tests.

**Alternatives considered**: Dual OpenAPI + Shine (rejected — OpenAPI token path removed).

---

## 4. Outbound request serialization

**Decision**: **Global FIFO queue** — at most **one** outbound Growatt HTTP request in flight for all work (reads, writes, health checks that hit Growatt, login/refresh) (FR-022). Implement with an **asyncio.Lock** or equivalent single-worker queue wrapping the low-level HTTP client so all call sites acquire the same gate.

**Rationale**: Spec mandates strict serialization; avoids race conditions on session cookies and simplifies reasoning.

**Alternatives considered**: Per-endpoint pools (violates FR-022); threading lock in sync client inside async app (possible but prefer one async-native critical section for consistency).

---

## 5. Upstream rate limiting (sliding 60s window)

**Decision**: Enforce **BRIDGE_RATE_LIMIT** as the maximum number of **completed** outbound Growatt HTTP requests in any rolling **60-second** window (FR-010). Use a **sliding-window** counter (e.g. deque of request timestamps or bucket algorithm) checked **before** issuing a new upstream call; if over budget, do **not** call Growatt — return **429** with `Retry-After` and `retry_after_seconds` in body (FR-008). **Health/readiness** traffic that contacts Growatt counts toward the same budget (FR-011).

**Rationale**: Matches SC-006 and clarifications (2026-04-04).

**Alternatives considered**: Token bucket (approximation, not identical to “any rolling 60s”); separate budget for health (rejected — spec says health counts).

---

## 6. Structured error envelope

**Decision**: Single **JSON error shape** for all bridge errors (codes, message, optional details); **never** expose raw upstream bodies/strings (FR-008). For **429**, include **`retry_after_seconds`** (integer) matching **`Retry-After`** header.

**Rationale**: Predictable client integration; auditability.

**Alternatives considered**: Pass-through upstream errors (rejected by FR-008).

---

## 7. Write readback

**Decision**: When `BRIDGE_REQUIRE_READBACK=true`, include **`readback.changed_fields`** as a map of field → `{before, after}` for fields that changed; omit when `false` (spec clarifications 2026-04-02).

**Rationale**: Confirms effect without clients parsing raw upstream.

---

## 8. Integration testing strategy

**Decision**: **pytest + httpx** (or FastAPI TestClient) against **real Growatt** for each approved endpoint before adding the next (FR-012). CI must have credentials/secrets available or tests skip with explicit marker.

**Rationale**: Spec mandates real API validation.

**Alternatives considered**: Record/replay only (insufficient per FR-012); full mock (dev UX only, not a gate for “next endpoint”).

---

## 9. Observability MVP

**Decision**: **Structured logging** + **append-only JSONL audit** for writes (FR-009, FR-023). **No** `/metrics` in MVP.

**Rationale**: Spec explicitly defers Prometheus.

---

## 10. Time representation

**Decision**: **UTC** instants as **ISO 8601** in JSON (FR-025). Historical daily/monthly buckets: labels and boundaries defined per CAP-04 empirical contract (FR-016, FR-025).

**Rationale**: Consistent automation client behavior across timezones.

---

## 11. Inverter writes — Shine `tcpSet.do` / `tlxSet`

**Decision**: Configuration writes use **`POST {base}/tcpSet.do`** with **`action=tlxSet`**, **`serialNum`**, **`type=<upstream parameter key>`**, and **`param1`…`param6`** as required by that `type`. The bridge exposes a **small, explicit catalog** of supported operations — including **nine** TOU operations **`time_segment1`…`time_segment9`** (one upstream `type` per slot, same `param` layout) plus non-TOU rows; **`BRIDGE_WRITE_ALLOWLIST`** lists permitted **`operation_id`** values (aligned with upstream `type` for MVP). Every write runs **readonly check → allowlist check → validation → upstream** (see `data-model.md` CAP-02).

**Rationale**: Matches captured portal traffic; keeps the bridge unable to send arbitrary `type=` strings; allowlist + validation satisfy FR-004/FR-005/FR-006.

**Alternatives considered**: OpenAPI V1 write endpoints (rejected — spec uses Shine session only); passthrough of any `type` (rejected — violates “strictly controlled” and FR-006).
