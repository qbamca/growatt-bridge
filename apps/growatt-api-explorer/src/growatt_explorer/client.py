"""Thin wrapper around growattServer for Legacy and OpenAPI V1."""

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def get_legacy_client():
    """Return a configured Legacy (ShinePhone) API client."""
    import growattServer

    api = growattServer.GrowattApi()
    server_url = os.getenv("GROWATT_SERVER_URL")
    if server_url:
        api.server_url = server_url.rstrip("/") + "/"
    return api


def get_openapi_v1_client():
    """Return a configured OpenAPI V1 client."""
    import growattServer

    token = os.getenv("GROWATT_API_TOKEN")
    if not token:
        raise ValueError("GROWATT_API_TOKEN is required for OpenAPI V1")
    api = growattServer.OpenApiV1(token=token)
    server_url = os.getenv("GROWATT_SERVER_URL")
    if server_url:
        api.server_url = server_url.rstrip("/") + "/"
    return api


def redact(data: Any, keys: frozenset | None = None) -> Any:
    """Redact sensitive keys from dict/list structures."""
    if keys is None:
        keys = frozenset(
            ("password", "token", "passwordcrc", "account", "accountname")
        )
    if isinstance(data, dict):
        return {
            k: "***" if k.lower() in keys else redact(v, keys)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact(item, keys) for item in data]
    return data
