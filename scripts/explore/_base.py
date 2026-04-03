"""Shared utilities for Growatt server exploration probes.

Each probe is a standalone script that makes one or more raw requests to the
Shine web portal and saves the full response for analysis. Responses are saved
to audit/explore/ (already gitignored) as timestamped JSON files.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RESPONSES_DIR = _REPO_ROOT / "audit" / "explore"

# Load .env from repo root once at import time
load_dotenv(_REPO_ROOT / ".env")


def require_env(*keys: str) -> dict[str, str]:
    """Load and return required env vars. Exits with a clear error if any are missing."""
    result: dict[str, str] = {}
    missing = []
    for key in keys:
        val = os.environ.get(key, "").strip()
        if not val:
            missing.append(key)
        else:
            result[key] = val
    if missing:
        print(f"ERROR: missing environment variable(s): {', '.join(missing)}", file=sys.stderr)
        print(f"  Set them in .env at the repo root.", file=sys.stderr)
        sys.exit(1)
    return result


def build_session(base_url: str) -> tuple[requests.Session, str]:
    """Return a fresh requests.Session and normalised base URL."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    })
    return session, base_url.rstrip("/") + "/"


def save_response(
    probe_name: str,
    resp: requests.Response,
    *,
    redact_keys: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Save the full response to audit/explore/<timestamp>_<probe_name>.json.

    Args:
        probe_name: Short identifier used in the filename and 'probe' field.
        resp:        The requests.Response to capture.
        redact_keys: Field names anywhere in the JSON body to replace with "***".
        extra:       Any additional metadata to include alongside the response.

    Returns:
        Path to the saved file.
    """
    _RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _RESPONSES_DIR / f"{ts}_{probe_name}.json"

    try:
        body: Any = resp.json()
    except Exception:
        body = resp.text

    if redact_keys and isinstance(body, dict):
        body = _redact_recursive(body, set(redact_keys))

    payload: dict[str, Any] = {
        "probe": probe_name,
        "timestamp": ts,
        "request": {
            "method": resp.request.method if resp.request else None,
            "url": str(resp.request.url) if resp.request else None,
        },
        "response": {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "cookies": {k: v for k, v in resp.cookies.items()},
            "body": body,
        },
    }
    if extra:
        payload["extra"] = extra

    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return out_path


def save_json_artifact(probe_name: str, payload: dict[str, Any]) -> Path:
    """Save a structured dict to audit/explore/<timestamp>_<probe_name>.json (no HTTP response)."""
    _RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _RESPONSES_DIR / f"{ts}_{probe_name}.json"
    envelope: dict[str, Any] = {
        "probe": probe_name,
        "timestamp": ts,
        **payload,
    }
    out_path.write_text(json.dumps(envelope, indent=2, default=str))
    return out_path


def print_section(label: str, data: Any) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(json.dumps(data, indent=2, default=str))


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def fail(msg: str) -> None:
    print(f"  \033[31m✗\033[0m {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"    {msg}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _redact_recursive(data: Any, keys: set[str]) -> Any:
    if isinstance(data, dict):
        return {k: "***" if k in keys else _redact_recursive(v, keys) for k, v in data.items()}
    if isinstance(data, list):
        return [_redact_recursive(item, keys) for item in data]
    return data
