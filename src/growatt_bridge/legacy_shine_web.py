"""Legacy Shine web portal client: POST tcpSet.do for MIN/TLX (tlxSet).

Used when OpenAPI ``v1/tlxSet`` returns ``error_useTrueHostToSet`` (10002) for a
plant. Session auth matches growattServer (newTwoLoginAPI.do + hashed password).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import requests

from growattServer import hash_password

logger = logging.getLogger(__name__)


def _is_session_invalid_tcp_response(body: dict[str, Any]) -> bool:
    """Return True when a failed tcpSet.do JSON indicates an expired portal session.

    Only treats explicit API failures (``success`` is false) with a matching
    message — ambiguous bodies are not classified as session expiry here.
    """
    if body.get("success") is not False:
        return False
    msg = body.get("msg") or body.get("result_msg") or body.get("resultMsg")
    if msg is None:
        return False
    s = str(msg).lower()
    return "login invalid" in s or "log in again" in s


def _looks_like_html_session_expiry(resp: requests.Response) -> bool:
    """Heuristic: non-JSON body that looks like an HTML login/error page."""
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in ct:
        return True
    text = (resp.text or "").lstrip()
    if text.startswith("<"):
        return True
    low = text.lower()
    return "<!doctype" in low or "<html" in low


def _log_json_parse_failure(resp: requests.Response, *, context: str, exc: BaseException) -> None:
    text = resp.text or ""
    preview = text[:2000]
    logger.warning(
        "growatt legacy JSON parse failed (%s): %s | status=%s url=%s "
        "content_type=%r content_length=%r",
        context,
        exc,
        resp.status_code,
        getattr(resp, "url", ""),
        resp.headers.get("Content-Type", ""),
        resp.headers.get("Content-Length", ""),
    )
    logger.debug(
        "growatt legacy JSON parse failed body_preview (%s): %r",
        context,
        preview,
    )


DEFAULT_WEB_BASE_URL = "https://server.growatt.com/"
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_MIN_DEVICE_TYPE = "7"


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
        self._op_lock = threading.Lock()

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

    def _invalidate_session(self) -> None:
        self._logged_in = False
        self._session.cookies.clear()

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

    def _request_json_with_session_retry(
        self,
        request_fn: Callable[[], requests.Response],
        *,
        context: str,
    ) -> Any:
        """Perform an authenticated legacy request and parse JSON; relogin once on HTML expiry."""
        with self._op_lock:
            self.ensure_logged_in()
            return self._response_json_with_relogin(request_fn, context=context, relogin_attempted=False)

    def _response_json_with_relogin(
        self,
        request_fn: Callable[[], requests.Response],
        *,
        context: str,
        relogin_attempted: bool,
    ) -> Any:
        resp = request_fn()
        resp.raise_for_status()
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            if (
                resp.status_code == 200
                and _looks_like_html_session_expiry(resp)
                and not relogin_attempted
            ):
                logger.info(
                    "legacy Shine web session likely expired (non-JSON body); "
                    "re-logging in and retrying | context=%s content_type=%r",
                    context,
                    resp.headers.get("Content-Type", ""),
                )
                self._invalidate_session()
                self.login()
                return self._response_json_with_relogin(
                    request_fn, context=context, relogin_attempted=True
                )
            _log_json_parse_failure(resp, context=context, exc=exc)
            raise

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
        data: dict[str, str] = {
            "action": "tlxSet",
            "serialNum": serial_num,
            "type": web_type,
        }
        merged = dict(params or {})
        for i in range(1, 20):
            key = f"param{i}"
            data[key] = str(merged.get(key, ""))

        logger.debug("legacy tcpSet.do type=%s serialNum=%s", web_type, serial_num)

        with self._op_lock:
            self.ensure_logged_in()
            self.set_plant_device_cookies(plant_id, serial_num)
            return self._tcp_set_post_with_retry(plant_id, serial_num, data, relogin_attempted=False)

    def _tcp_set_post_with_retry(
        self,
        plant_id: str,
        serial_num: str,
        data: dict[str, str],
        *,
        relogin_attempted: bool,
    ) -> dict[str, Any]:
        url = f"{self._base}tcpSet.do"
        resp = self._session.post(url, data=data, timeout=self._timeout)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            return {}
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return {"success": False, "msg": text, "_non_json_body": True}

        if not relogin_attempted and _is_session_invalid_tcp_response(body):
            logger.info(
                "legacy Shine web session invalid; re-logging in and retrying tcpSet.do",
            )
            self._invalidate_session()
            self.login()
            self.set_plant_device_cookies(plant_id, serial_num)
            return self._tcp_set_post_with_retry(plant_id, serial_num, data, relogin_attempted=True)
        return body

    def tcp_set_scalar(
        self,
        plant_id: str,
        serial_num: str,
        web_type: str,
        param1: str,
    ) -> dict[str, Any]:
        """Single-value MIN parameter write (param1 only, rest empty)."""
        return self.tcp_set_tlx(plant_id, serial_num, web_type, params={"param1": param1})

    def plant_list(self) -> list[dict[str, Any]]:
        """List all plants via newTwoPlantAPI.do?op=getAllPlantListTwo."""
        def req() -> requests.Response:
            return self._session.post(
                f"{self._base}newTwoPlantAPI.do",
                params={"op": "getAllPlantListTwo"},
                data={"language": "1", "order": "1", "pageSize": "15", "toPageNum": "1"},
                timeout=self._timeout,
            )

        body = self._request_json_with_session_retry(
            req,
            context="newTwoPlantAPI.do op=getAllPlantListTwo",
        )
        return body.get("PlantList", [])

    def plant_details(self, plant_id: str) -> dict[str, Any]:
        """Get plant settings via newPlantAPI.do?op=getPlant."""
        def req() -> requests.Response:
            return self._session.get(
                f"{self._base}newPlantAPI.do",
                params={"op": "getPlant", "plantId": plant_id},
                timeout=self._timeout,
            )

        body = self._request_json_with_session_retry(
            req,
            context=f"newPlantAPI.do op=getPlant plantId={plant_id!r}",
        )
        return body.get("obj") or body

    def tlx_detail(self, device_sn: str) -> dict[str, Any]:
        """Get live MIN/TLX inverter data via newTlxApi.do?op=getTlxDetailData."""
        def req() -> requests.Response:
            return self._session.get(
                f"{self._base}newTlxApi.do",
                params={"op": "getTlxDetailData", "id": device_sn},
                timeout=self._timeout,
            )

        body = self._request_json_with_session_retry(
            req,
            context=f"newTlxApi.do getTlxDetailData id={device_sn!r}",
        )
        return body.get("data") or body.get("obj") or body

    def read_settings_bean(self, serial_num: str) -> dict[str, Any]:
        """Return the full tlxSetBean for a MIN/TLX device via getTlxSetData."""
        def req() -> requests.Response:
            return self._session.post(
                f"{self._base}newTlxApi.do",
                params={"op": "getTlxSetData"},
                data={"serialNum": serial_num},
                timeout=self._timeout,
            )

        body = self._request_json_with_session_retry(
            req,
            context=f"newTlxApi.do getTlxSetData serialNum={serial_num!r}",
        )
        return body.get("obj", {}).get("tlxSetBean") or {}

    def device_list(self, plant_id: str) -> list[dict[str, Any]]:
        """Get the list of devices for a plant via newTwoPlantAPI.do.

        Mirrors ``GrowattApi.device_list``: tries ``getAllDeviceListTwo`` first,
        falls back to ``getAllDeviceList`` when the primary response is empty
        (TLX systems).
        """
        def req_two() -> requests.Response:
            return self._session.get(
                f"{self._base}newTwoPlantAPI.do",
                params={
                    "op": "getAllDeviceListTwo",
                    "plantId": plant_id,
                    "pageNum": 1,
                    "pageSize": 1,
                },
                timeout=self._timeout,
            )

        body = self._request_json_with_session_retry(
            req_two,
            context=f"newTwoPlantAPI.do op=getAllDeviceListTwo plantId={plant_id!r}",
        )
        devices = body.get("deviceList", [])
        if not devices:
            def req_fallback() -> requests.Response:
                return self._session.get(
                    f"{self._base}newTwoPlantAPI.do",
                    params={
                        "op": "getAllDeviceList",
                        "plantId": plant_id,
                        "language": 1,
                    },
                    timeout=self._timeout,
                )

            body2 = self._request_json_with_session_retry(
                req_fallback,
                context=f"newTwoPlantAPI.do op=getAllDeviceList plantId={plant_id!r}",
            )
            raw = body2.get("deviceList", [])
            devices = list(raw.values()) if isinstance(raw, dict) else raw
        return devices if isinstance(devices, list) else []

    def read_time_segments(self, serial_num: str) -> list[dict[str, Any]]:
        """Read TOU time-segment schedule via newTlxApi.do?op=getTlxSetData.

        Returns a list of up to 9 segment dicts with keys ``segment``, ``mode``,
        ``start_time`` (HH:MM), ``end_time`` (HH:MM), and ``enabled``.
        """
        def req() -> requests.Response:
            return self._session.post(
                f"{self._base}newTlxApi.do",
                params={"op": "getTlxSetData"},
                data={"serialNum": serial_num},
                timeout=self._timeout,
            )

        body = self._request_json_with_session_retry(
            req,
            context=f"newTlxApi.do getTlxSetData (time segments) serialNum={serial_num!r}",
        )
        bean = body.get("obj", {}).get("tlxSetBean") or {}
        segments: list[dict[str, Any]] = []
        for i in range(1, 10):
            start = bean.get(f"forcedTimeStart{i}")
            end = bean.get(f"forcedTimeStop{i}")
            if start is None and end is None:
                continue
            mode_raw = bean.get(f"time{i}Mode")
            try:
                mode = int(mode_raw) if mode_raw is not None else 0
            except (TypeError, ValueError):
                mode = 0
            switch_raw = bean.get(f"forcedStopSwitch{i}")
            try:
                enabled = bool(int(switch_raw)) if switch_raw is not None else True
            except (TypeError, ValueError):
                enabled = True
            segments.append(
                {
                    "segment": i,
                    "mode": mode,
                    "start_time": str(start) if start is not None else None,
                    "end_time": str(end) if end is not None else None,
                    "enabled": enabled,
                }
            )
        return segments

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
