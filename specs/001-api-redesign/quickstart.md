# Quickstart: 001-api-redesign

Local run and smoke checks for developers working on the redesigned API.

## Prerequisites

- Python ≥3.11
- Network access to Growatt Cloud (integration tests and manual checks use **real** credentials per FR-012)
- Environment variables (see [spec.md § Environment Variables](../spec.md#environment-variables))

## Install

From the repository root:

```bash
pip install -e ".[dev]"
```

## Configure

Copy `.env` from project docs or create one with at least:

| Variable | Notes |
|----------|--------|
| `GROWATT_WEB_USERNAME` | Shine portal user |
| `GROWATT_WEB_PASSWORD` | Plain password (hashed before upstream login) |
| `GROWATT_DEVICE_SN` | Device serial for path validation |
| `GROWATT_PLANT_ID` | Plant id for upstream context |
| `BRIDGE_READONLY` | `true` default; `false` to allow writes (with allowlist) |
| `BRIDGE_RATE_LIMIT` | Optional; default **20** upstream calls per rolling **60s** |

## Run the server

```bash
uvicorn growatt_bridge.main:create_app --factory --host 0.0.0.0 --port 8081
```

(Or use the Docker image / Compose stack defined for deployment.)

## Versioned request example

Replace the media type with the value documented in OpenAPI when v1 is wired:

```bash
curl -sS -H 'Accept: application/vnd.growatt-bridge.v1+json' \
  "http://localhost:8081/devices"
```

## Write request example (CAP-02)

Use the same vendor media type for **`Accept`** and **`Content-Type`**. Body shape is **`{ "operation", "parameters" }`** — see [data-model.md § Write endpoint (client HTTP)](../data-model.md#write-endpoint-client-http) and [contracts/write-request.schema.json](./contracts/write-request.schema.json).

```bash
DEVICE_SN="YOUR_SERIAL"
curl -sS -X POST \
  -H 'Accept: application/vnd.growatt-bridge.v1+json' \
  -H 'Content-Type: application/vnd.growatt-bridge.v1+json' \
  -d '{"operation":"ub_ac_charging_stop_soc","parameters":{"stop_soc":42}}' \
  "http://localhost:8081/devices/${DEVICE_SN}/write"
```

Dry-run validation only (no upstream write — FR-007):

```bash
curl -sS -X POST \
  -H 'Accept: application/vnd.growatt-bridge.v1+json' \
  -H 'Content-Type: application/vnd.growatt-bridge.v1+json' \
  -d '{"operation":"ac_charge","parameters":{"enabled":true}}' \
  "http://localhost:8081/devices/${DEVICE_SN}/write/validate"
```

Requires `BRIDGE_READONLY=false` and the operation listed in `BRIDGE_WRITE_ALLOWLIST` for the mutating `/write` call.

## Tests

```bash
pytest
```

Real-API tests require credentials in the environment (or are skipped by markers). Follow FR-012: each new endpoint ships with a passing real-API test before the next endpoint is added.

## Where to read more

- Feature requirements: [spec.md](../spec.md)
- Research decisions: [research.md](../research.md)
- Entities: [data-model.md](../data-model.md)
- HTTP contracts: [contracts/](./contracts/)
