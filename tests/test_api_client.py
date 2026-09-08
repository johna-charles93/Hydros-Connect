"""Unit tests for the HYDROS Public API client (custom_components.hydros.api)."""

from __future__ import annotations

import json

import pytest

from custom_components.hydros.api import (
    HydrosApiAuthError,
    HydrosApiError,
    HydrosApiRateLimitError,
    HydrosApiStateUnavailable,
    HydrosPublicApiClient,
    HydrosSession,
    _decode_body,
    device_identifier,
    extract_device,
)
from homeassistant.util import dt as dt_util


class _FakeResponse:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    """Minimal stand-in for aiohttp.ClientSession."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: list[dict] = []

    def request(self, method, url, *, params=None, json=None, headers=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "params": params, "json": json, "headers": headers}
        )
        status, body = self._handler(method, url, params, json, headers)
        return _FakeResponse(status, body)


def _client(handler) -> tuple[HydrosPublicApiClient, _FakeSession]:
    session = _FakeSession(handler)
    client = HydrosPublicApiClient(
        session,  # type: ignore[arg-type]
        provider_key="prov_abc",
        device_key="dev_xyz",
        base_url="https://api.example.test",
    )
    return client, session


DEVICE = {"deviceId": "a0b7", "friendlyName": "Reef", "type": "X4"}


@pytest.mark.parametrize(
    "payload",
    [
        DEVICE,
        [DEVICE],
        {"device": DEVICE},
        {"data": DEVICE},
        {"devices": [DEVICE]},
        {"items": [DEVICE]},
        json.dumps(DEVICE),  # double-encoded string body
        {"id": "a0b7", "friendlyName": "Reef"},  # alt id key
        {"mac": "d0:ef:76", "friendlyName": "Reef"},
    ],
)
def test_extract_device_tolerates_shapes(payload) -> None:
    got = extract_device(payload)
    assert isinstance(got, dict)
    assert device_identifier(got) != ""


@pytest.mark.parametrize("payload", [None, [], {}, {"foo": "bar"}, "not json", 42])
def test_extract_device_rejects_non_devices(payload) -> None:
    assert extract_device(payload) is None


def test_decode_body_unwraps_double_encoded_json() -> None:
    assert _decode_body(json.dumps(json.dumps({"a": 1}))) == {"a": 1}
    assert _decode_body('{"a": 1}') == {"a": 1}
    assert _decode_body("") is None
    assert _decode_body("plain text") == "plain text"


async def test_get_device_accepts_wrapped_list_payload() -> None:
    client, _ = _client(lambda *_: (200, json.dumps({"devices": [DEVICE]})))
    device = await client.async_get_device()
    assert device_identifier(device) == "a0b7"


async def test_get_device_raises_with_shape_hint_on_garbage() -> None:
    client, _ = _client(lambda *_: (200, '{"totallyDifferent": true}'))
    with pytest.raises(HydrosApiError) as excinfo:
        await client.async_get_device()
    assert "dict" in str(excinfo.value)


async def test_get_device_sends_v1_auth_header() -> None:
    client, session = _client(
        lambda *_: (200, '{"deviceId": "a0b7", "friendlyName": "Reef", "type": "X4"}')
    )
    device = await client.async_get_device()

    assert device["deviceId"] == "a0b7"
    assert session.calls[0]["headers"]["Authorization"] == "prov_abc:dev_xyz"
    assert session.calls[0]["url"] == "https://api.example.test/api/v1/device"


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, HydrosApiAuthError),
        (403, HydrosApiAuthError),
        (429, HydrosApiRateLimitError),
        (500, HydrosApiError),
    ],
)
async def test_error_status_mapping(status: int, exc: type[Exception]) -> None:
    client, _ = _client(lambda *_: (status, '{"error": "nope"}'))
    with pytest.raises(exc):
        await client.async_get_device()


async def test_probe_write_permission_true_and_false() -> None:
    writable, _ = _client(lambda *_: (202, "{}"))
    assert await writable.async_probe_write_permission() is True

    readonly, _ = _client(lambda *_: (403, '{"error": "Forbidden: this device key is read-only"}'))
    assert await readonly.async_probe_write_permission() is False


async def test_start_session_parses_fields() -> None:
    body = (
        '{"pollUrl": "https://api.example.test/api/v1/device/state?id=sess-1",'
        ' "pollToken": "jwt-token", "durationSeconds": 21600,'
        ' "pollIntervalSeconds": 30, "expiresAt": "2099-01-01T00:00:00Z"}'
    )
    client, _ = _client(lambda *_: (200, body))
    session = await client.async_start_session()

    assert isinstance(session, HydrosSession)
    assert session.poll_url.endswith("id=sess-1")
    assert session.poll_token == "jwt-token"
    assert session.poll_interval_seconds == 30
    assert session.needs_renew(0) is False


async def test_poll_state_uses_bearer_token_and_maps_404() -> None:
    session = HydrosSession(
        poll_url="https://api.example.test/api/v1/device/state?id=sess-1",
        poll_token="jwt-token",
        poll_interval_seconds=30,
        expires_at=dt_util.utcnow(),
        started_at=dt_util.utcnow(),
    )

    ok_client, cap = _client(lambda *_: (200, '{"mode": "Normal"}'))
    state = await ok_client.async_poll_state(session)
    assert state["mode"] == "Normal"
    assert cap.calls[0]["headers"]["Authorization"] == "Bearer jwt-token"

    offline_client, _ = _client(lambda *_: (404, '{"error": "No state available"}'))
    with pytest.raises(HydrosApiStateUnavailable):
        await offline_client.async_poll_state(session)


async def test_get_retries_once_on_gateway_5xx_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(*_):
        calls["n"] += 1
        if calls["n"] == 1:
            return (503, '{"message": "Service Unavailable"}')
        return (200, '{"deviceId": "a0b7", "friendlyName": "Reef", "type": "X4"}')

    client, session = _client(handler)
    device = await client.async_get_device()

    assert device["deviceId"] == "a0b7"
    assert len(session.calls) == 2  # retried once


async def test_get_gives_up_after_retry_and_reports_status() -> None:
    client, session = _client(lambda *_: (502, '{"message": "Bad Gateway"}'))
    with pytest.raises(HydrosApiError) as excinfo:
        await client.async_get_device()

    assert excinfo.value.status == 502
    assert len(session.calls) == 2


async def test_write_requests_are_not_retried() -> None:
    client, session = _client(lambda *_: (503, '{"message": "Service Unavailable"}'))
    with pytest.raises(HydrosApiError):
        await client.async_put_overrides({"k": 1})

    assert len(session.calls) == 1  # no retry on PUT


async def test_send_command_body_shapes() -> None:
    client, session = _client(lambda *_: (202, '{"command": "Feeding", "published": true, "deviceConnected": true}'))

    await client.async_send_command("mode", "Feeding")
    assert session.calls[-1]["json"] == {"command": "Feeding"}
    assert session.calls[-1]["url"].endswith("/api/v1/device/overrides/mode/command")

    await client.async_send_command("uuid-1", "dose", value=250, receipt=True)
    assert session.calls[-1]["json"] == {"command": "dose", "value": 250}
    assert session.calls[-1]["params"] == {"receipt": "1"}
