from __future__ import annotations

"""Async client for the official CoralVue HYDROS Public API.

Docs: https://developers.api.coralvuehydros.com  (OpenAPI: /specs/hydros-public-api.yaml)

Every provider endpoint is scoped to a single device by the device key, so this
client is constructed per config entry and needs no device identifier.

Authentication (V1 "simple"):

    Authorization: {provider_key}:{device_key}

The state-poll endpoint is the one exception — it takes the short-lived poll
token minted by ``POST /api/v1/device/state/session`` as a Bearer token instead.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_API_REQUEST_TIMEOUT,
    HYDROS_API_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


class HydrosApiError(Exception):
    """Base error for HYDROS Public API calls."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class HydrosApiAuthError(HydrosApiError):
    """401/403 — credentials are missing, invalid, or lack permission.

    Never retry with the same credentials.
    """


class HydrosApiRateLimitError(HydrosApiError):
    """429 — a per-device, per-endpoint rate limit was exceeded.

    Always transient; back off and retry.
    """


class HydrosApiStateUnavailable(HydrosApiError):
    """404 from the state poll — no cached state (device offline / no session)."""


@dataclass(slots=True)
class HydrosSession:
    """A REST polling session opened via ``POST /api/v1/device/state/session``."""

    poll_url: str
    poll_token: str
    poll_interval_seconds: int
    expires_at: datetime
    started_at: datetime

    def needs_renew(self, margin_seconds: float) -> bool:
        return dt_util.utcnow() >= self.expires_at - _timedelta(margin_seconds)


def _timedelta(seconds: float):
    from datetime import timedelta

    return timedelta(seconds=seconds)


def _parse_expires_at(value: Any, *, fallback_seconds: int) -> datetime:
    if isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return dt_util.utcnow() + _timedelta(fallback_seconds)


class HydrosPublicApiClient:
    """Thin async wrapper over the HYDROS Public API.

    Args:
        session: A shared ``aiohttp.ClientSession`` (use
            ``homeassistant.helpers.aiohttp_client.async_get_clientsession``).
        provider_key: The caller's provider key (per-user; keep secret).
        device_key: The device owner's device key, scoped to one device.
        base_url: Override for tests.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        provider_key: str,
        device_key: str,
        base_url: str = HYDROS_API_BASE_URL,
    ) -> None:
        self._session = session
        self._provider_key = provider_key.strip()
        self._device_key = device_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=DEFAULT_API_REQUEST_TIMEOUT)

    # -- low-level ---------------------------------------------------------

    def _auth_header(self) -> str:
        """V1 simple provider auth: ``{provider_key}:{device_key}``."""
        return f"{self._provider_key}:{self._device_key}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        authorization: str | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        headers = {"Authorization": authorization or self._auth_header()}
        # Retry a GET once on a transient gateway failure (cold Lambda authorizer,
        # CloudFront/API-Gateway 5xx, a dropped connection). Writes are never
        # retried automatically.
        attempts = 2 if method.upper() == "GET" else 1

        last_transport_error: Exception | None = None
        for attempt in range(attempts):
            try:
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self._timeout,
                ) as resp:
                    status = resp.status
                    text = await resp.text()
            except aiohttp.ClientError as err:
                last_transport_error = HydrosApiError(
                    f"HTTP transport error calling {method} {path}: {err}"
                )
            except asyncio.TimeoutError as err:  # noqa: F841
                last_transport_error = HydrosApiError(f"Timed out calling {method} {path}")
            else:
                if status in expected:
                    return _decode_body(text)
                if status in (502, 503, 504) and attempt + 1 < attempts:
                    await asyncio.sleep(1.0)
                    continue

                body = _decode_body(text)
                message = _error_message(body) or f"{method} {path} returned HTTP {status}"
                if status in (401, 403):
                    raise HydrosApiAuthError(message, status=status)
                if status == 429:
                    raise HydrosApiRateLimitError(message, status=status)
                if status == 404:
                    raise HydrosApiStateUnavailable(message, status=status)
                raise HydrosApiError(message, status=status)

            if attempt + 1 < attempts:
                await asyncio.sleep(1.0)

        assert last_transport_error is not None
        raise last_transport_error

    # -- devices --------------------------------------------------------

    async def async_get_device(self) -> dict[str, Any]:
        """``GET /api/v1/device`` — the single device bound to the device key."""
        result = await self._request("GET", "/api/v1/device")
        if not isinstance(result, dict):
            raise HydrosApiError("Unexpected /device payload")
        return result

    # -- polling session + state --------------------------------------

    async def async_start_session(self) -> HydrosSession:
        """``POST /api/v1/device/state/session`` — mint a 6h poll token and wake the device."""
        result = await self._request("POST", "/api/v1/device/state/session")
        if not isinstance(result, dict) or "pollUrl" not in result or "pollToken" not in result:
            raise HydrosApiError("Unexpected session response")

        now = dt_util.utcnow()
        duration = int(result.get("durationSeconds") or 21600)
        return HydrosSession(
            poll_url=str(result["pollUrl"]),
            poll_token=str(result["pollToken"]),
            poll_interval_seconds=int(result.get("pollIntervalSeconds") or 30),
            expires_at=_parse_expires_at(result.get("expiresAt"), fallback_seconds=duration),
            started_at=now,
        )

    async def async_poll_state(self, session: HydrosSession) -> dict[str, Any]:
        """``GET`` the session's ``pollUrl`` with the poll token as Bearer.

        Raises :class:`HydrosApiStateUnavailable` when the device has no cached
        state (offline, or the session was never started).
        """
        result = await self._request(
            "GET",
            session.poll_url,
            authorization=f"Bearer {session.poll_token}",
        )
        if not isinstance(result, dict):
            raise HydrosApiError("Unexpected /device/state payload")
        return result

    # -- overrides ----------------------------------------------------

    async def async_get_override_metadata(self) -> list[dict[str, Any]]:
        """``GET /api/v1/device/overrides/metadata`` — overridable outputs + the ``mode`` entry."""
        result = await self._request("GET", "/api/v1/device/overrides/metadata")
        if not isinstance(result, list):
            raise HydrosApiError("Unexpected override metadata payload")
        return [entry for entry in result if isinstance(entry, dict)]

    async def async_get_overrides(self) -> dict[str, Any]:
        """``GET /api/v1/device/overrides`` — current override doc + delivery status."""
        result = await self._request("GET", "/api/v1/device/overrides")
        if not isinstance(result, dict):
            raise HydrosApiError("Unexpected overrides payload")
        return result

    async def async_put_overrides(
        self, mapping: dict[str, Any], *, receipt: bool = False
    ) -> dict[str, Any]:
        """``PUT /api/v1/device/overrides`` — merge-set / clear (``null``) overrides by key.

        An empty ``mapping`` is a documented no-op and is used as a safe
        write-permission probe.
        """
        params = {"receipt": "1"} if receipt else None
        result = await self._request(
            "PUT",
            "/api/v1/device/overrides",
            params=params,
            json_body=mapping,
            expected=(200, 202),
        )
        return result if isinstance(result, dict) else {}

    async def async_delete_override(self, key: str, *, receipt: bool = False) -> dict[str, Any]:
        """``DELETE /api/v1/device/overrides/{key}`` — return one output to auto/schedule."""
        params = {"receipt": "1"} if receipt else None
        result = await self._request(
            "DELETE",
            f"/api/v1/device/overrides/{key}",
            params=params,
            expected=(200, 202),
        )
        return result if isinstance(result, dict) else {}

    async def async_send_command(
        self,
        key: str,
        command: str,
        *,
        value: int | None = None,
        receipt: bool = False,
    ) -> dict[str, Any]:
        """``POST /api/v1/device/overrides/{key}/command`` — momentary command / mode flip.

        Use ``key="mode"`` and ``command=<mode name>`` to change operating mode.
        """
        body: dict[str, Any] = {"command": command}
        if value is not None:
            body["value"] = int(value)
        params = {"receipt": "1"} if receipt else None
        result = await self._request(
            "POST",
            f"/api/v1/device/overrides/{key}/command",
            params=params,
            json_body=body,
            expected=(200, 202),
        )
        return result if isinstance(result, dict) else {}

    # -- helpers ----------------------------------------------------

    async def async_probe_write_permission(self) -> bool:
        """Return ``True`` if the device key is write-scoped.

        Sends ``PUT /overrides`` with an empty body — a documented no-op that
        still runs the permission check. ``403`` means read-only.
        """
        try:
            await self.async_put_overrides({})
        except HydrosApiAuthError as err:
            if err.status == 403:
                return False
            raise
        return True


def _decode_body(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _error_message(body: Any) -> str | None:
    if isinstance(body, dict):
        msg = body.get("error") or body.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    if isinstance(body, str) and body.strip():
        return body.strip()[:200]
    return None
