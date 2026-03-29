# External References

Index of external documentation for the Growatt Cloud API and growatt-bridge. PDF copies live in `docs/references/` for offline access. Online-only sources are listed by URL.

---

## PDF Downloads

Download these into `docs/references/` and commit them for offline access. They are not hosted in this repo by default because they are third-party documents.

### Growatt Server Open API Protocol Standards

- **URL**: https://growatt.pl/wp-content/uploads/2020/01/Growatt-Server-Open-API-protocol-standards.pdf
- **Source**: growatt.pl (Polish Growatt distributor)
- **Local path**: `docs/references/growatt-server-open-api-protocol-standards.pdf`
- **Contents**: Official Growatt cloud API protocol — user, plant, and equipment endpoints. Describes the legacy API structure and some V1 endpoints. The primary official reference for the API contract.

```bash
curl -L -o docs/references/growatt-server-open-api-protocol-standards.pdf \
  "https://growatt.pl/wp-content/uploads/2020/01/Growatt-Server-Open-API-protocol-standards.pdf"
```

### Growatt Server API Guide

- **URL**: https://www.amosplanet.org/wp-content/uploads/2023/05/Growatt-Server-API-Guide.pdf
- **Source**: amosplanet.org
- **Local path**: `docs/references/growatt-server-api-guide.pdf`
- **Contents**: Community-compiled API guide. Supplements the official protocol doc with additional endpoint examples and response field notes.

```bash
curl -L -o docs/references/growatt-server-api-guide.pdf \
  "https://www.amosplanet.org/wp-content/uploads/2023/05/Growatt-Server-API-Guide.pdf"
```

### Growatt Export Limitation Guide

- **URL**: https://growatt.pl/wp-content/uploads/2020/01/Growatt-Export-Limitation-Guide.pdf
- **Source**: growatt.pl (Polish Growatt distributor)
- **Local path**: `docs/references/growatt-export-limitation-guide.pdf`
- **Contents**: Official guide to the export limit feature — meter wiring, RS485 connection, and parameter configuration. Essential before changing export-limit settings on any installation.

```bash
curl -L -o docs/references/growatt-export-limitation-guide.pdf \
  "https://growatt.pl/wp-content/uploads/2020/01/Growatt-Export-Limitation-Guide.pdf"
```

### TLX Export Limit Guide

- **URL**: https://www.raystech.com.au/wp-content/uploads/TLX-Export-limit.pdf
- **Source**: Raystech (Australian Growatt reseller)
- **Local path**: `docs/references/tlx-export-limit.pdf`
- **Contents**: Configuration guide specifically for the TLX/MIN family (type 7). Documents `exportLimit`, `exportLimitPowerRate`, and `backFlowSingleCtrl` parameters in detail. Required reading before automating export limits.

```bash
curl -L -o docs/references/tlx-export-limit.pdf \
  "https://www.raystech.com.au/wp-content/uploads/TLX-Export-limit.pdf"
```

### Download all at once

```bash
mkdir -p docs/references
curl -L -o docs/references/growatt-server-open-api-protocol-standards.pdf \
  "https://growatt.pl/wp-content/uploads/2020/01/Growatt-Server-Open-API-protocol-standards.pdf"
curl -L -o docs/references/growatt-server-api-guide.pdf \
  "https://www.amosplanet.org/wp-content/uploads/2023/05/Growatt-Server-API-Guide.pdf"
curl -L -o docs/references/growatt-export-limitation-guide.pdf \
  "https://growatt.pl/wp-content/uploads/2020/01/Growatt-Export-Limitation-Guide.pdf"
curl -L -o docs/references/tlx-export-limit.pdf \
  "https://www.raystech.com.au/wp-content/uploads/TLX-Export-limit.pdf"
```

---

## Online References

These sources are referenced by URL only; they are not downloaded.

### Growatt Showdoc API (English)

- **URL**: https://www.showdoc.com.cn/262556420217021/1494053950115877
- **Password**: 123456
- **Contents**: Growatt cloud API documentation in English hosted on Showdoc. Covers OpenAPI V1 endpoints including `min_*` methods and response schemas.

### Growatt Showdoc API (Chinese)

- **URL**: https://www.showdoc.com.cn/v1?page_id=1426329703603439
- **Password**: 123456
- **Contents**: Same API documentation in Chinese. Sometimes has more complete coverage than the English version.

### OpenAPI Portal

- **URL**: https://openapi.growatt.com/
- **Contents**: Growatt OpenAPI V1 developer portal. Token generation, endpoint explorer, and registration. Requires a Growatt distributor, installer, or user account.

### OpenAPI Registration

- **URL**: https://openapi.growatt.com/register
- **Contents**: Register for OpenAPI V1 access as Distributor, Installer, or User.

### growattServer (GitHub)

- **URL**: https://github.com/indykoning/PyPi_GrowattServer
- **Contents**: Community Python client library wrapping both Legacy and OpenAPI V1. The `growatt-bridge` uses this library. Reference implementation for understanding the full API surface, especially `shinephone.md` and `openapiv1.md` in the docs directory.

---

## Internal Documentation

| Document | Description |
|----------|-------------|
| `docs/growatt-cloud-api.md` | API variant overview, endpoint catalog, device type mapping |
| `docs/parameter-glossary.md` | Field-level documentation for all API response properties, organized by domain |
| `docs/parameters/time-segments.md` | TOU schedule deep-dive (segment format, modes, write API) |
| `docs/parameters/charge-discharge.md` | Battery charge/discharge settings and safe ranges |
| `docs/parameters/export-limit.md` | Export limitation feature — meter requirements and parameter mapping |
| `docs/parameters/battery-policy.md` | SOC limits, AC charge, winter mode |
| `docs/parameters/safety-constraints.md` | What must never be changed via the API, and why |
| `docs/security.md` | Threat model and risk mitigations |
| `docs/openclaw-integration.md` | How to deploy growatt-bridge alongside OpenClaw |
