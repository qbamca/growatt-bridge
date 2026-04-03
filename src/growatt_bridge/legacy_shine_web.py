"""Legacy Shine web portal client: POST tcpSet.do for MIN/TLX (tlxSet).

Used when OpenAPI ``v1/tlxSet`` returns ``error_useTrueHostToSet`` (10002) for a
plant. Session auth matches growattServer (newTwoLoginAPI.do + hashed password).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import requests

from growattServer import hash_password

logger = logging.getLogger(__name__)

DEFAULT_WEB_BASE_URL = "https://server.growatt.com/"
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_MIN_DEVICE_TYPE = "7"

# Shine panel TLX telemetry (browser XHR to ``/panel/tlx/…_bdc``).
_XHR_JSON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}


class LegacyShineWebError(Exception):
    """Raised when legacy web login or tcpSet fails in a non-HTTP way."""


class LegacyShineWebClient:
    """Logged-in session to server.growatt.com-style hosts for tcpSet.do writes."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password_plain: str,
        *,
        user_agent: str = _DEFAULT_UA,
        timeout_s: float = 60.0,
    ) -> None:
        self._base = base_url.rstrip("/") + "/"
        self._username = username
        self._password_plain = password_plain
        self._timeout = timeout_s
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._logged_in = False

    @property
    def base_url(self) -> str:
        return self._base

    def login(self) -> None:
        """Authenticate via newTwoLoginAPI.do (same contract as growattServer.GrowattApi)."""
        pw = hash_password(self._password_plain)
        url = f"{self._base}newTwoLoginAPI.do"
        resp = self._session.post(
            url,
            data={"userName": self._username, "password": pw},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        back = body.get("back") or {}
        if not back.get("success"):
            msg = back.get("msg") or "login failed"
            raise LegacyShineWebError(str(msg))
        self._logged_in = True

    def ensure_logged_in(self) -> None:
        if not self._logged_in:
            self.login()

    def set_plant_device_cookies(
        self,
        plant_id: str,
        serial_num: str,
        device_type: str = _MIN_DEVICE_TYPE,
    ) -> None:
        """Mirror portal context cookies before tcpSet (selected plant + device)."""
        host = urlparse(self._base).hostname
        if not host:
            return
        path = "/"
        self._session.cookies.set("selectedPlantId", str(plant_id), domain=host, path=path)
        self._session.cookies.set("memoryDeviceType", str(device_type), domain=host, path=path)
        self._session.cookies.set("memoryDeviceSn", serial_num, domain=host, path=path)

    def read_all_min_param_raw(
        self,
        plant_id: str,
        serial_num: str,
    ) -> requests.Response:
        """POST tcpSet.do with ``action=readAllMinParam``; returns the HTTP response."""
        self.ensure_logged_in()
        self.set_plant_device_cookies(plant_id, serial_num)

        url = f"{self._base}tcpSet.do"
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        data = {"action": "readAllMinParam", "serialNum": serial_num}
        logger.debug("legacy tcpSet.do readAllMinParam serialNum=%s", serial_num)
        return self._session.post(
            url,
            data=data,
            headers=headers,
            timeout=self._timeout,
        )

    def read_all_min_param(self, plant_id: str, serial_num: str) -> dict[str, Any]:
        """POST tcpSet.do with action=readAllMinParam (MIN inverter settings snapshot)."""
        resp = self.read_all_min_param_raw(plant_id, serial_num)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"success": False, "msg": text, "_non_json_body": True}

    def tcp_set_tlx(
        self,
        plant_id: str,
        serial_num: str,
        web_type: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST tcpSet.do with action=tlxSet, serialNum, type, param1..param19.

        *params* maps ``param1``..``param19`` to string values; omitted keys default
        to empty string (same padding as growattServer OpenAPI MIN writes).
        """
        self.ensure_logged_in()
        self.set_plant_device_cookies(plant_id, serial_num)

        data: dict[str, str] = {
            "action": "tlxSet",
            "serialNum": serial_num,
            "type": web_type,
        }
        merged = dict(params or {})
        for i in range(1, 20):
            key = f"param{i}"
            data[key] = str(merged.get(key, ""))

        url = f"{self._base}tcpSet.do"
        logger.debug("legacy tcpSet.do type=%s serialNum=%s", web_type, serial_num)
        resp = self._session.post(url, data=data, timeout=self._timeout)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"success": False, "msg": text, "_non_json_body": True}

    def tcp_set_scalar(
        self,
        plant_id: str,
        serial_num: str,
        web_type: str,
        param1: str,
    ) -> dict[str, Any]:
        """Single-value MIN parameter write (param1 only, rest empty)."""
        return self.tcp_set_tlx(plant_id, serial_num, web_type, params={"param1": param1})

    def tcp_set_time_segment(
        self,
        plant_id: str,
        serial_num: str,
        segment_id: int,
        batt_mode: int,
        start_h: int,
        start_m: int,
        end_h: int,
        end_m: int,
        enabled: bool,
    ) -> dict[str, Any]:
        """TOU slot write: type ``time_segment{N}``, param1..param6 per growattServer MIN."""
        web_type = f"time_segment{segment_id}"
        return self.tcp_set_tlx(
            plant_id,
            serial_num,
            web_type,
            params={
                "param1": str(batt_mode),
                "param2": str(start_h),
                "param3": str(start_m),
                "param4": str(end_h),
                "param5": str(end_m),
                "param6": "1" if enabled else "0",
            },
        )

    def new_tlx_api_post_raw(
        self,
        op: str,
        form: dict[str, str],
        *,
        plant_id: str | None = None,
        serial_num: str | None = None,
    ) -> requests.Response:
        """POST ``newTlxApi.do?op=…`` — TLX JSON APIs that accept the web session (see growattServer).

        When *plant_id* and *serial_num* are provided, :meth:`set_plant_device_cookies`
        is applied first (same portal context as ``tcpSet.do`` / panel XHR).
        """
        self.ensure_logged_in()
        if plant_id is not None and serial_num is not None:
            self.set_plant_device_cookies(plant_id, serial_num)
        url = f"{self._base}newTlxApi.do"
        return self._session.post(
            url,
            params={"op": op},
            data=form,
            timeout=self._timeout,
        )

    def get_tlx_status_data_bdc_raw(
        self,
        plant_id: str,
        serial_num: str,
        *,
        allow_redirects: bool = True,
    ) -> requests.Response:
        """POST ``panel/tlx/getTLXStatusData_bdc`` — live TLX status (portal XHR).

        **Note:** On ``server.growatt.com``, this path may return **302 → errorNoLogin**
        unless the session includes the same cookies as a full browser session after
        loading the SPA. For programmatic capture, prefer :meth:`new_tlx_api_post_raw`
        with ``op=getSystemStatus_KW``. Optional browser cookie paste: set env
        ``GROWATT_BROWSER_COOKIE`` in ``fetch_tlx_telemetry.py`` before calling.
        """
        self.ensure_logged_in()
        self.set_plant_device_cookies(plant_id, serial_num)
        url = f"{self._base}panel/tlx/getTLXStatusData_bdc?plantId={plant_id}"
        headers = {
            **_XHR_JSON_HEADERS,
            "Referer": f"{self._base}index",
        }
        return self._session.post(
            url,
            data={"tlxSn": serial_num},
            headers=headers,
            timeout=self._timeout,
            allow_redirects=allow_redirects,
        )

    def get_tlx_total_data_bdc_raw(
        self,
        plant_id: str,
        serial_num: str,
        *,
        allow_redirects: bool = True,
    ) -> requests.Response:
        """POST ``panel/tlx/getTLXTotalData_bdc`` — TLX cumulative / total energy (portal XHR).

        Same session caveats as :meth:`get_tlx_status_data_bdc_raw`. For programmatic
        capture, prefer ``new_tlx_api_post_raw`` with ``op=getEnergyOverview``.
        """
        self.ensure_logged_in()
        self.set_plant_device_cookies(plant_id, serial_num)
        url = f"{self._base}panel/tlx/getTLXTotalData_bdc?plantId={plant_id}"
        headers = {
            **_XHR_JSON_HEADERS,
            "Referer": f"{self._base}index",
        }
        return self._session.post(
            url,
            data={"tlxSn": serial_num},
            headers=headers,
            timeout=self._timeout,
            allow_redirects=allow_redirects,
        )
