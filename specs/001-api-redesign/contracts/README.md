# API contracts: 001-api-redesign

Machine- and human-readable contracts for the redesigned bridge HTTP API.

| Artifact | Purpose |
|----------|---------|
| [versioning.md](./versioning.md) | `Accept` / `Content-Type` version negotiation (FR-021) |
| [error-envelope.schema.json](./error-envelope.schema.json) | JSON Schema for structured error bodies (FR-008) |

The running service also exposes **OpenAPI** (FastAPI) at `/docs` / `/openapi.json`; every permitted route must be documented with schemas and supported `Accept` values (FR-002).
