# Growatt Cloud API Explorer

Exploration tool for the Growatt Cloud API. Gathers documentation, tests endpoints (Legacy and OpenAPI V1), and validates assumptions for the Solar Ops Agent project.

## Setup

1. **Python 3.10+** required.

2. **Create a virtual environment** (recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   # or: .venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   # or: pip install growattServer python-dotenv requests
   ```

4. **Configure credentials** — copy `.env.example` to `.env` and fill in:

   ```bash
   cp .env.example .env
   ```

## Obtaining Credentials

### Legacy API (username / password)

- Use the same login as the **ShinePhone** or **Growatt Shinecloud** app.
- Not the OpenAPI dashboard; use the mobile app or Shinecloud web portal credentials.

### OpenAPI V1 (token)

- Open the **ShinePhone** app.
- Go to **Me** (bottom right) > tap your account name > **API Token**.
- Copy the token into `GROWATT_API_TOKEN` in `.env`.

## Running Scripts

From the `apps/growatt-api-explorer` directory:

```bash
# Generate/update internal docs (links, endpoint catalog)
python scripts/fetch_docs.py

# Test Legacy API (requires GROWATT_USERNAME, GROWATT_PASSWORD)
python scripts/test_legacy.py

# Test OpenAPI V1 (requires GROWATT_API_TOKEN)
python scripts/test_openapi_v1.py
```

Test scripts print API responses with secrets redacted. Use the output to confirm endpoint behavior and update `docs/growatt-cloud-api.md` as needed.

## Regional Servers

Set `GROWATT_SERVER_URL` in `.env` for non-EU accounts:

- China: `https://openapi-cn.growatt.com/`
- North America: `https://openapi-us.growatt.com/`
- Europe (default): `https://openapi.growatt.com/`

## Output

- `scripts/fetch_docs.py` writes to `docs/growatt-cloud-api.md`.
- Test scripts log to stdout. Update internal docs with findings (verified responses, rate limits, error codes).

## Reference

- [growattServer](https://github.com/indykoning/PyPi_GrowattServer) — Python reference implementation
- [Internal API docs](../../docs/growatt-cloud-api.md) — growatt-cloud-api.md
