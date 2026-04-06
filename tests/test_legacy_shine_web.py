"""Unit tests for LegacyShineWebClient session recovery (tcpSet + JSON reads)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from growatt_bridge.legacy_shine_web import (
    LegacyShineWebClient,
    _is_session_invalid_tcp_response,
    _looks_like_html_session_expiry,
)


def test_is_session_invalid_tcp_response_positive() -> None:
    assert _is_session_invalid_tcp_response(
        {"success": False, "msg": "Login invalid, please log in again"}
    )


def test_is_session_invalid_tcp_response_alt_phrase() -> None:
    assert _is_session_invalid_tcp_response(
        {"success": False, "msg": "Please log in again"}
    )


def test_is_session_invalid_tcp_response_only_login_invalid() -> None:
    assert _is_session_invalid_tcp_response(
        {"success": False, "msg": "Login invalid"}
    )


def test_is_session_invalid_tcp_response_unrelated_msg() -> None:
    assert not _is_session_invalid_tcp_response(
        {"success": False, "msg": "Parameter out of range"}
    )


def test_is_session_invalid_tcp_response_missing_success() -> None:
    assert not _is_session_invalid_tcp_response({"msg": "Login invalid, please log in again"})


def test_is_session_invalid_tcp_response_success_true() -> None:
    assert not _is_session_invalid_tcp_response(
        {"success": True, "msg": "Login invalid, please log in again"}
    )


def _html_response() -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.headers = {"Content-Type": "text/html; charset=utf-8"}
    r.text = "\n\n<!DOCTYPE html><html><body>login</body></html>"
    r.url = "https://server.growatt.com/newTwoPlantAPI.do"

    def json_fail() -> None:
        raise json.JSONDecodeError("Expecting value", r.text, 0)

    r.json = json_fail
    r.raise_for_status = MagicMock()
    return r


def _json_response(payload: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.headers = {"Content-Type": "application/json;charset=UTF-8"}
    r.text = json.dumps(payload)
    r.url = "https://server.growatt.com/x"
    r.json = lambda: payload
    r.raise_for_status = MagicMock()
    return r


def test_looks_like_html_session_expiry() -> None:
    r = _html_response()
    assert _looks_like_html_session_expiry(r)


@pytest.fixture
def client() -> LegacyShineWebClient:
    return LegacyShineWebClient("https://server.growatt.com/", "user", "secret")


def test_tcp_set_relogin_on_session_invalid_message(client: LegacyShineWebClient) -> None:
    client._logged_in = True
    posts: list[MagicMock] = []

    def post_side_effect(*_a, **_kw) -> MagicMock:
        n = len(posts)
        if n == 0:
            m = MagicMock()
            m.status_code = 200
            m.text = '{"success": false, "msg": "Login invalid, please log in again"}'
            m.raise_for_status = MagicMock()
            posts.append(m)
            return m
        m = MagicMock()
        m.status_code = 200
        m.text = '{"success": true, "msg": "ok"}'
        m.raise_for_status = MagicMock()
        posts.append(m)
        return m

    with patch.object(client._session, "post", side_effect=post_side_effect):
        with patch.object(client, "login", autospec=True) as login_mock:
            out = client.tcp_set_tlx("plant-1", "SN1", "ac_charge", params={"param1": "1"})

    assert out == {"success": True, "msg": "ok"}
    assert login_mock.call_count == 1
    assert len(posts) == 2


def test_tcp_set_no_relogin_on_unrelated_failure(client: LegacyShineWebClient) -> None:
    client._logged_in = True

    m = MagicMock()
    m.status_code = 200
    m.text = '{"success": false, "msg": "Some other error"}'
    m.raise_for_status = MagicMock()

    with patch.object(client._session, "post", return_value=m):
        with patch.object(client, "login", autospec=True) as login_mock:
            out = client.tcp_set_tlx("plant-1", "SN1", "ac_charge", params={"param1": "1"})

    assert out["success"] is False
    login_mock.assert_not_called()


def test_plant_list_html_then_json_after_relogin(client: LegacyShineWebClient) -> None:
    client._logged_in = True
    seq = iter([_html_response(), _json_response({"PlantList": [{"plantId": "p1"}]})])

    with patch.object(client._session, "post", side_effect=lambda *a, **k: next(seq)):
        with patch.object(client, "login", autospec=True) as login_mock:
            plants = client.plant_list()

    assert plants == [{"plantId": "p1"}]
    assert login_mock.call_count == 1


def test_device_list_html_then_json(client: LegacyShineWebClient) -> None:
    client._logged_in = True
    seq = iter(
        [
            _html_response(),
            _json_response({"deviceList": [{"device_sn": "D1"}]}),
        ]
    )

    with patch.object(client._session, "get", side_effect=lambda *a, **k: next(seq)):
        with patch.object(client, "login", autospec=True) as login_mock:
            devices = client.device_list("plant-9")

    assert devices == [{"device_sn": "D1"}]
    assert login_mock.call_count == 1


def test_tlx_detail_html_then_json(client: LegacyShineWebClient) -> None:
    client._logged_in = True
    seq = iter(
        [
            _html_response(),
            _json_response({"data": {"sn": "X1", "power": "1"}}),
        ]
    )

    with patch.object(client._session, "get", side_effect=lambda *a, **k: next(seq)):
        with patch.object(client, "login", autospec=True) as login_mock:
            detail = client.tlx_detail("X1")

    assert detail == {"sn": "X1", "power": "1"}
    assert login_mock.call_count == 1


def test_read_json_html_twice_raises_no_loop(client: LegacyShineWebClient) -> None:
    client._logged_in = True
    h = _html_response()

    with patch.object(client._session, "post", return_value=h):
        with patch.object(client, "login", autospec=True) as login_mock:
            with pytest.raises(json.JSONDecodeError):
                client.plant_list()

    assert login_mock.call_count == 1
