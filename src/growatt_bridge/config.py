"""Application configuration via pydantic-settings.

All settings are driven by environment variables (or a .env file at the repo
root).  No config files are required — set the variables and go.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .legacy_shine_web import DEFAULT_WEB_BASE_URL

# ── Write operation IDs ────────────────────────────────────────────────────────
# The complete set of named operations the safety layer understands.
# Only IDs from this set may appear in BRIDGE_WRITE_ALLOWLIST.
VALID_WRITE_OPERATIONS: frozenset[str] = frozenset(
    {
        "set_ac_charge_stop_soc",
    }
)


class Settings(BaseSettings):
    """Bridge configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ── Growatt Cloud ──────────────────────────────────────────────────────────
    growatt_api_token: Annotated[
        str,
        Field(description="OpenAPI V1 token (from ShinePhone app)."),
    ]

    growatt_server_url: Annotated[
        str,
        Field(
            default="https://openapi.growatt.com/",
            description="Regional Growatt Cloud URL.",
        ),
    ]

    growatt_device_sn: Annotated[
        str | None,
        Field(
            default=None,
            description="Default device serial number (skip discovery in single-device setups).",
        ),
    ]

    growatt_plant_id: Annotated[
        str | None,
        Field(
            default=None,
            description="Default plant ID.",
        ),
    ]

    # ── Legacy Shine web (tcpSet.do) for MIN writes when OpenAPI tlxSet returns 10002 ─
    bridge_legacy_web_min_writes: Annotated[
        bool,
        Field(
            default=False,
            validation_alias=AliasChoices(
                "GROWATT_LEGACY_WEB_MIN_WRITES",
                "BRIDGE_LEGACY_WEB_MIN_WRITES",
            ),
            description=(
                "When true, all MIN parameter and time-segment writes use the legacy "
                "Shine portal tcpSet.do path instead of OpenAPI v1/tlxSet."
            ),
        ),
    ]

    growatt_web_base_url: Annotated[
        str,
        Field(
            default=DEFAULT_WEB_BASE_URL,
            validation_alias=AliasChoices("GROWATT_WEB_BASE_URL"),
            description="Shine web portal base URL (e.g. https://server.growatt.com/).",
        ),
    ]

    growatt_web_username: Annotated[
        str | None,
        Field(
            default=None,
            validation_alias=AliasChoices("GROWATT_WEB_USERNAME"),
            description="Shine web / dashboard username (same hashing as legacy growattServer login).",
        ),
    ]

    growatt_web_password: Annotated[
        str | None,
        Field(
            default=None,
            validation_alias=AliasChoices("GROWATT_WEB_PASSWORD"),
            description="Shine web portal password (plain text; hashed before login).",
        ),
    ]

    # ── Bridge HTTP ────────────────────────────────────────────────────────────
    bridge_port: Annotated[
        int,
        Field(default=8081, ge=1, le=65535, description="HTTP listen port."),
    ]

    bridge_host: Annotated[
        str,
        Field(default="0.0.0.0", description="HTTP bind address."),
    ]

    # ── Safety / Write Control ─────────────────────────────────────────────────
    bridge_readonly: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "When true (default), all write endpoints return 403. "
                "Set to false AND populate bridge_write_allowlist to enable writes."
            ),
        ),
    ]

    bridge_write_allowlist: Annotated[
        str,
        Field(
            default="",
            description=(
                "Comma-separated list of write operation IDs that are permitted. "
                "Example: set_ac_charge_stop_soc. "
                "Empty string means no writes even if bridge_readonly=false."
            ),
        ),
    ]

    bridge_rate_limit_writes: Annotated[
        int,
        Field(
            default=3,
            ge=1,
            description="Maximum number of write operations permitted per minute.",
        ),
    ]

    bridge_require_readback: Annotated[
        bool,
        Field(
            default=True,
            description="Re-read config after every write and include diff in response.",
        ),
    ]

    bridge_audit_log: Annotated[
        Path,
        Field(
            default=Path("/var/log/growatt-bridge/audit.jsonl"),
            description="Path for the append-only JSONL audit log.",
        ),
    ]

    # ── Validators ─────────────────────────────────────────────────────────────

    @field_validator("growatt_server_url", "growatt_web_base_url")
    @classmethod
    def _normalise_server_url(cls, v: str) -> str:
        """Ensure the URL ends with a trailing slash."""
        return v.rstrip("/") + "/"

    @field_validator("bridge_write_allowlist", mode="before")
    @classmethod
    def _normalise_allowlist(cls, v: object) -> str:
        """Normalise the raw env value to a plain string for storage.

        pydantic-settings would otherwise attempt to JSON-decode a list[str]
        field, which fails for comma-separated env var values.  We store the
        raw string and parse it on demand via parsed_write_allowlist().
        """
        if isinstance(v, list):
            return ",".join(str(i).strip() for i in v if str(i).strip())
        return str(v) if v else ""

    # ── Convenience helpers ────────────────────────────────────────────────────

    def parsed_write_allowlist(self) -> list[str]:
        """Return the allowlist as a validated list of operation IDs.

        Raises ValueError if an unknown operation ID is present.
        """
        if not self.bridge_write_allowlist:
            return []
        items = [item.strip() for item in self.bridge_write_allowlist.split(",") if item.strip()]
        unknown = sorted(set(items) - VALID_WRITE_OPERATIONS)
        if unknown:
            raise ValueError(
                f"Unknown write operation IDs in BRIDGE_WRITE_ALLOWLIST: {unknown}. "
                f"Valid IDs are: {sorted(VALID_WRITE_OPERATIONS)}"
            )
        return items

    def is_operation_allowed(self, operation_id: str) -> bool:
        """Return True only if writes are enabled and operation_id is allowlisted."""
        if self.bridge_readonly:
            return False
        try:
            return operation_id in self.parsed_write_allowlist()
        except ValueError:
            return False

    def redacted_token(self) -> str:
        """Return a safely redacted version of the API token for logging."""
        t = self.growatt_api_token
        if len(t) <= 8:
            return "***"
        return t[:4] + "***" + t[-4:]
