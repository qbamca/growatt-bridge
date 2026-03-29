"""Tokenless reachability checks against Growatt Cloud (no API quota)."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

DEFAULT_CLOUD_CHECK_TIMEOUT_S = 5.0


def growatt_host_reachable(
    base_url: str,
    *,
    timeout: float = DEFAULT_CLOUD_CHECK_TIMEOUT_S,
) -> tuple[bool, str | None]:
    """Return ``(True, None)`` if the Growatt host answers over HTTPS without auth.

    Any completed HTTP response (including 4xx/5xx) counts as reachable: TLS and
    TCP succeeded. Connection, DNS, timeout, and TLS verification errors return
    ``(False, message)``. Does **not** validate the API token.
    """
    url = base_url.strip().rstrip("/") + "/"
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        try:
            return True, None
        finally:
            resp.close()
    except requests.RequestException as exc:
        msg = str(exc)
        logger.debug("Growatt host check failed for %s: %s", url, msg)
        return False, msg
