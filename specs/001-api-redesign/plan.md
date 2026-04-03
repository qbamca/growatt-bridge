# Implementation Plan: Growatt Bridge API Redesign

**Branch**: `001-api-redesign` | **Date**: 2026-04-03 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/001-api-redesign/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Redesign the Growatt bridge HTTP API as a **strict, documented facade** over the Shine web portal (session-based auth). The bridge exposes a **fixed allowlist** of endpoints, **normalized** responses across device families (MIN/TLX vs SPH/MIX), **header-based API versioning** (no `/v1` URL prefix), **global serialization** of all outbound Growatt HTTP (at most one in flight), a **sliding 60-second upstream rate limit** (default 20 requests), structured errors (including **429** with `Retry-After` and body), **append-only JSONL audit** for writes, and **real-Growatt integration tests** per endpoint before adding the next. Implementation continues in the existing **Python / FastAPI** codebase (`src/growatt_bridge/`).

## Technical Context

**Language/Version**: Python ≥3.11 (see `pyproject.toml` `requires-python`)  
**Primary Dependencies**: FastAPI ≥0.115, Uvicorn, Pydantic v2, pydantic-settings, requests, growattServer (password hashing / legacy helpers as needed)  
**Storage**: N/A for application state (stateless HTTP except in-memory session cookies and queues); **append-only JSONL file** for write audit (`BRIDGE_AUDIT_LOG`)  
**Testing**: pytest ≥8, httpx (async client for tests), pytest-asyncio; **integration tests against real Growatt** per FR-012  
**Target Platform**: Linux (Docker / WSL2); bridge listens on configurable host/port (default `0.0.0.0:8081`), plain HTTP for MVP on private Docker network  
**Project Type**: web-service (HTTP API facade)  
**Performance Goals**: Correctness and upstream contract compliance over throughput; concurrent inbound requests are queued; bounded by global serialization + sliding-window upstream cap  
**Constraints**: At most one outbound Growatt HTTP request in flight (FR-022); sliding 60s window upstream budget (FR-010); no raw upstream errors to clients (FR-008); UTC ISO 8601 for instants (FR-025); no Prometheus metrics in MVP (FR-023); no write idempotency in MVP (FR-024)  
**Scale/Scope**: Single plant / single configured device via env; endpoint set grows incrementally with empirical CAP contracts (CAP-01–CAP-04)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repository `.specify/memory/constitution.md` is still a **placeholder template** (not ratified project principles). **Interim compliance** is judged against this feature spec’s functional requirements (FR-001–FR-025) and success criteria (SC-001–SC-012).

| Gate | Status | Notes |
|------|--------|--------|
| Bounded API surface | Pass | FR-001, FR-006; surface-area test (SC-005) |
| Documentation & contracts | Pass | FR-002, FR-021; OpenAPI + spec `contracts/` |
| Normalization & errors | Pass | FR-003, FR-008; no raw upstream leakage |
| Safety (readonly, allowlist, validate) | Pass | FR-004–FR-007 |
| Upstream rate limit & serialization | Pass | FR-010, FR-022; sliding window + single-flight queue |
| Session auth (Shine) | Pass | FR-017–FR-018; remove OpenAPI token path per clarifications |
| Observability MVP | Pass | FR-009, FR-023; logs + audit JSONL only |
| Real API tests per endpoint | Pass | FR-012 | |

**Post–Phase 1**: Design artifacts (`data-model.md`, `contracts/`, `quickstart.md`) align with FRs; no unresolved NEEDS CLARIFICATION items in Technical Context.

## Project Structure

### Documentation (this feature)

```text
specs/001-api-redesign/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/growatt_bridge/
├── __init__.py
├── main.py                 # FastAPI app factory, middleware, router registration
├── config.py               # Settings (env)
├── client.py               # Growatt upstream client (session, HTTP)
├── connectivity.py
├── legacy_shine_web.py     # Shine web flows (evolving per redesign)
├── models.py               # Pydantic models
├── safety.py               # Readonly, allowlist, validation
├── routes/
│   ├── health.py
│   ├── plants.py
│   ├── devices.py
│   ├── telemetry.py
│   ├── config_read.py
│   ├── commands.py
│   └── write_operations.py
tests/
├── conftest.py             # (as added) fixtures for real API tests
└── ...
pyproject.toml
requirements.txt
Dockerfile
docs/                       # Parameter glossary, etc.
```

**Structure Decision**: Single Python package under `src/growatt_bridge/` with route modules; tests under `tests/`. No separate frontend. API redesign refactors routes, client, and safety to match the new spec without introducing a second deployable.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No additional complexity beyond the spec’s explicit requirements (global queue + sliding window + Shine session management). Table left empty.

## Phase 2 (forward reference)

Implementation task breakdown and ordered delivery live in **`tasks.md`**, generated by **`/speckit.tasks`**, not by this plan command.
