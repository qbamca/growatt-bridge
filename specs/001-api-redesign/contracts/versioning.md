# Version negotiation (FR-021)

## Rules

- **No** API version in the URL path (no `/v1/` prefix).
- Clients **MUST** send an `Accept` header that includes a supported **vendor media type** for JSON.
- Successful responses **MUST** use a matching `Content-Type` for the negotiated version.
- If `Accept` does not allow any supported version, the bridge **MUST** respond with **406 Not Acceptable** and a structured error body listing supported media types (FR-021, FR-008).

## Example (v1)

**Request**

```http
GET /devices HTTP/1.1
Host: localhost:8081
Accept: application/vnd.growatt-bridge.v1+json
```

**Response (success)**

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.growatt-bridge.v1+json
```

The exact vendor string(s) **MUST** be listed in OpenAPI (`responses` content types) and kept in sync with middleware (FR-002).

## Evolution

Adding v2: introduce `application/vnd.growatt-bridge.v2+json`, document migration, and keep v1 until deprecated by project policy.
