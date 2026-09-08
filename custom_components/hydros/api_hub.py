from __future__ import annotations

"""Hub backed by the official CoralVue HYDROS Public API (REST polling).

This is the non-legacy data path. It speaks to https://api.coralvuehydros.com
with a per-user provider key + a device-owner device key, and exposes the same
surface the entity platforms already consume from
:class:`~custom_components.hydros.hydros_hub.HydrosHub` so the platform code is
shared between both paths.

Differences from the legacy hub, by design:

* One config entry == one device (the device key is device-scoped). ``collective_ids``
  always has exactly one element.
* State is **polled** every ~30s via a short-lived session token — there is no
  MQTT push. Entities fall ``unavailable`` on their normal staleness window when
  polling stops or the device goes offline (``404`` from the state endpoint).
* Output/entity modelling is synthesised from ``GET /device/overrides/metadata``
  plus the live state document, since the API has no rich S3 config download.
* No dosing-log endpoint, so ``supports_dosing_history`` is ``False`` and the
  per-doser "Dosed Today" sensors are not created. Manual dosing uses the
  first-class ``dose`` command instead of the on/sleep/off toggle.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import (
    HydrosApiAuthError,
    HydrosApiError,
    HydrosApiRateLimitError,
    HydrosApiStateUnavailable,
    HydrosPublicApiClient,
    HydrosSession,
    device_identifier,
)
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_KEY,
    CONF_KEY_PERMISSION,
    CONF_PROVIDER_KEY,
    DEFAULT_API_METADATA_TTL,
    DEFAULT_API_POLL_INTERVAL,
    DEFAULT_API_SESSION_RENEW_MARGIN,
    DEFAULT_COMMAND_CONFIRM_TIMEOUT,
    DEFAULT_MODE_COMMAND_COOLDOWN_SECONDS,
    DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS,
    KEY_PERMISSION_WRITE,
    SIGNAL_COLLECTIVE_UPDATED,
    SIGNAL_CONFIG_UPDATED,
)
from .hub_base import HydrosHubBase

_LOGGER = logging.getLogger(__name__)

_OUTPUT_STATE_ALIASES = {"off": 0, "on": 1, "auto": -1}
# HYDROS reports output levels as 0..10000 (10000 == full on).
_LEVEL_MAX = 10000


@dataclass
class _Command:
    command_id: str
    command_type: str  # "mode" | "output"
    target_key: str
    expected_value: Any
    issued_at: datetime
    api_ack_at: datetime | None = None
    confirmed_at: datetime | None = None
    status: str = "pending"  # pending | api_acked | confirmed | failed | timed_out
    error: str | None = None
    last_observed_value: Any = None


@dataclass
class _OverrideMeta:
    """Flattened override-metadata entry keyed by user-visible output name."""

    key: str
    name: str
    otype: str  # "bool" | "level" | "flag" | "mode" | other
    minimum: int = 0
    maximum: int = _LEVEL_MAX
    commands: dict[str, Any] = field(default_factory=dict)
    dose_arg: tuple[int, int] | None = None
    parent: str | None = None


class HydrosApiHub(HydrosHubBase):
    """Coordinate HYDROS Public API access for Home Assistant."""

    supports_dosing_history = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._device_id: str = str(entry.data[CONF_DEVICE_ID]).strip()
        self._provider_key: str = str(entry.data[CONF_PROVIDER_KEY])
        self._device_key: str = str(entry.data[CONF_DEVICE_KEY])
        self._write_capable: bool = (
            str(entry.data.get(CONF_KEY_PERMISSION, KEY_PERMISSION_WRITE)).lower()
            == KEY_PERMISSION_WRITE
        )

        self.collective_ids: list[str] = [self._device_id]

        self._client: HydrosPublicApiClient | None = None
        self._session: HydrosSession | None = None
        self._poll_lock = asyncio.Lock()
        self._unsub_poll = None

        self._device_meta: dict[str, Any] = {}
        self._status_payload: dict[str, Any] = {}
        self._status_received: datetime | None = None
        self._message_count = 0
        self._device_offline = False

        self._override_meta: dict[str, _OverrideMeta] = {}  # by output name
        self._mode_commands: list[str] = []
        self._metadata_fetched_at: datetime | None = None
        self._metadata_dirty = False

        self._synth_config: dict[str, Any] = {}
        self._synth_keys: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())

        self._commands: dict[tuple[str, str], _Command] = {}
        self._last_output_command_at: dict[str, datetime] = {}
        self._last_mode_command_at: datetime | None = None

        self._api_last_success: datetime | None = None
        self._api_last_error: str | None = None
        self._api_last_error_at: datetime | None = None

        self._debug_sample: dict[str, Any] | None = None

    # -- lifecycle ------------------------------------------------------

    @property
    def entry_id(self) -> str:
        return self._entry.entry_id

    async def async_setup(self) -> None:
        session = async_get_clientsession(self._hass)
        self._client = HydrosPublicApiClient(
            session,
            provider_key=self._provider_key,
            device_key=self._device_key,
        )

        # Identity is required — without it the device can't be set up at all.
        try:
            self._device_meta = await self._client.async_get_device()
        except HydrosApiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HydrosApiError as err:
            raise ConfigEntryNotReady(f"HYDROS API GET /device failed: {err}") from err

        _LOGGER.debug(
            "HYDROS device for %s: keys=%s", self._device_id, sorted(self._device_meta)
        )

        # Metadata / session / first poll are best-effort: bring the entry up
        # even if they fail so the entities exist (unavailable) and the poll
        # loop can keep retrying. A stuck ConfigEntryNotReady here would hide a
        # non-transient server-side problem behind an endless retry with no
        # visible detail.
        for label, step in (
            ("override metadata", self._async_refresh_metadata),
            ("state session", self._async_start_session),
            ("initial state poll", self._async_poll_once),
        ):
            try:
                await step()
            except HydrosApiAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except HydrosApiError as err:
                _LOGGER.warning(
                    "HYDROS API setup step '%s' failed for %s: %s — the "
                    "integration will load and keep retrying in the background",
                    label,
                    self._device_id,
                    err,
                )
                self._note_error(err)

        self._build_synth_config()

        interval = max(
            DEFAULT_API_POLL_INTERVAL,
            self._session.poll_interval_seconds if self._session else DEFAULT_API_POLL_INTERVAL,
        )
        self._unsub_poll = async_track_time_interval(
            self._hass, self._handle_interval, timedelta(seconds=interval)
        )

    async def async_unload(self) -> None:
        if self._unsub_poll is not None:
            self._unsub_poll()
            self._unsub_poll = None
        self._client = None
        self._session = None
        self._status_payload = {}
        self._override_meta.clear()
        self._synth_config = {}

    # -- polling ------------------------------------------------------

    async def _handle_interval(self, _now: datetime) -> None:
        await self._async_poll()

    async def _async_start_session(self) -> None:
        assert self._client is not None
        try:
            self._session = await self._client.async_start_session()
        except HydrosApiRateLimitError:
            if self._session is not None and not self._session.needs_renew(0):
                _LOGGER.warning(
                    "Hydros session-start rate limited; reusing existing session for %s",
                    self._device_id,
                )
                return
            raise

    async def _async_ensure_session(self) -> None:
        if self._session is None or self._session.needs_renew(DEFAULT_API_SESSION_RENEW_MARGIN):
            await self._async_start_session()

    async def _async_poll_once(self) -> None:
        """First poll during setup."""
        if self._client is None or self._session is None:
            return
        try:
            state = await self._client.async_poll_state(self._session)
        except HydrosApiStateUnavailable:
            # Device has not reported yet; come up and let polling catch it.
            self._device_offline = True
            return
        self._apply_state(state)

    async def _async_poll(self) -> None:
        if self._client is None:
            return
        async with self._poll_lock:
            try:
                if self._metadata_dirty or self._metadata_stale():
                    await self._async_refresh_metadata()
                await self._async_ensure_session()
                assert self._session is not None
                try:
                    state = await self._client.async_poll_state(self._session)
                except HydrosApiAuthError:
                    # Poll token expired/rotated — re-mint once and retry.
                    await self._async_start_session()
                    state = await self._client.async_poll_state(self._session)
            except HydrosApiStateUnavailable as err:
                self._device_offline = True
                self._note_error(err)
                self._dispatch()
                return
            except HydrosApiRateLimitError as err:
                self._note_error(err)
                return
            except HydrosApiAuthError as err:
                # Persistent auth failure — surface as reauth.
                self._note_error(err)
                self._entry.async_start_reauth(self._hass)
                return
            except HydrosApiError as err:
                self._note_error(err)
                return

            self._device_offline = False
            self._apply_state(state)
            self._note_success()
            self._maybe_rebuild_synth_config()
            self._reconcile_commands(state)
            self._dispatch()

    def _metadata_stale(self) -> bool:
        if self._metadata_fetched_at is None:
            return True
        age = (dt_util.utcnow() - self._metadata_fetched_at).total_seconds()
        return age > DEFAULT_API_METADATA_TTL

    async def _async_refresh_metadata(self) -> None:
        assert self._client is not None
        entries = await self._client.async_get_override_metadata()
        by_name: dict[str, _OverrideMeta] = {}
        mode_commands: list[str] = []

        for entry in entries:
            name = str(entry.get("name") or entry.get("key") or "").strip()
            key = str(entry.get("key") or "").strip()
            otype = str(entry.get("type") or "").strip().lower()
            if not key:
                continue

            if otype == "mode":
                commands = entry.get("commands")
                if isinstance(commands, dict):
                    mode_commands = [str(m) for m in commands.keys()]
                continue

            if not name:
                continue

            commands = entry.get("commands") if isinstance(entry.get("commands"), dict) else {}
            dose_arg: tuple[int, int] | None = None
            dose_spec = commands.get("dose") if isinstance(commands, dict) else None
            if isinstance(dose_spec, dict) and isinstance(dose_spec.get("arg"), dict):
                arg = dose_spec["arg"]
                try:
                    dose_arg = (int(arg.get("min", 1)), int(arg.get("max", _LEVEL_MAX)))
                except (TypeError, ValueError):
                    dose_arg = (1, _LEVEL_MAX)

            by_name[name] = _OverrideMeta(
                key=key,
                name=name,
                otype=otype,
                minimum=_safe_int(entry.get("min"), 0),
                maximum=_safe_int(entry.get("max"), _LEVEL_MAX),
                commands=commands or {},
                dose_arg=dose_arg,
                parent=(str(entry["parent"]) if entry.get("parent") else None),
            )

        self._override_meta = by_name
        self._mode_commands = mode_commands
        self._metadata_fetched_at = dt_util.utcnow()
        self._metadata_dirty = False

    # -- state bookkeeping ------------------------------------------

    def _apply_state(self, state: dict[str, Any]) -> None:
        self._status_payload = _merge_payloads(self._status_payload, state)
        self._status_received = dt_util.utcnow()
        self._message_count += 1

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def _note_success(self) -> None:
        self._api_last_success = self._utcnow()

    def _note_error(self, err: Exception) -> None:
        self._api_last_error = str(err)
        self._api_last_error_at = self._utcnow()

    @callback
    def _dispatch(self) -> None:
        async_dispatcher_send(self._hass, self.signal_for_collective(self._device_id), self._device_id)

    @callback
    def _dispatch_config(self) -> None:
        async_dispatcher_send(self._hass, self.signal_for_config(self._device_id), self._device_id)

    # -- synthesised config --------------------------------------

    def _current_io_keys(self) -> tuple[frozenset[str], frozenset[str]]:
        inputs = self._status_payload.get("Input") or self._status_payload.get("input") or {}
        outputs = self._status_payload.get("Output") or self._status_payload.get("output") or {}
        in_keys = frozenset(inputs) if isinstance(inputs, dict) else frozenset()
        out_keys = frozenset(outputs) if isinstance(outputs, dict) else frozenset()
        out_keys = out_keys | frozenset(self._override_meta)
        return in_keys, out_keys

    def _maybe_rebuild_synth_config(self) -> None:
        keys = self._current_io_keys()
        if keys != self._synth_keys:
            self._build_synth_config()
            self._dispatch_config()

    def _build_synth_config(self) -> None:
        inputs_payload = self._status_payload.get("Input") or self._status_payload.get("input") or {}
        outputs_payload = self._status_payload.get("Output") or self._status_payload.get("output") or {}

        synth_inputs: dict[str, Any] = {}
        if isinstance(inputs_payload, dict):
            for name, payload in inputs_payload.items():
                meta = {"friendlyName": name, "label": name}
                meta.update(_classify_input(name, payload if isinstance(payload, dict) else {}))
                synth_inputs[name] = meta

        synth_outputs: dict[str, Any] = {}
        output_names = set()
        if isinstance(outputs_payload, dict):
            output_names.update(outputs_payload.keys())
        output_names.update(self._override_meta.keys())

        for name in output_names:
            payload = outputs_payload.get(name, {}) if isinstance(outputs_payload, dict) else {}
            meta: dict[str, Any] = {"friendlyName": name, "name": name}
            om = self._override_meta.get(name)
            if om is not None:
                meta["_hydros_key"] = om.key
                meta["_hydros_type"] = om.otype
                if om.otype == "level":
                    meta["type"] = "o10vpump"
                    meta["family"] = "vpump"
                    meta["minValue"] = om.minimum
                    meta["maxValue"] = om.maximum
                elif om.otype == "bool":
                    meta["type"] = "outlet"
                    meta["family"] = "outlet"
                    # Clearing an override returns the output to schedule/auto.
                    meta["autoControl"] = True
                if "dose" in om.commands:
                    meta["_hydros_is_doser"] = True
                    meta["family"] = "doser"
                if om.parent:
                    meta["parent"] = om.parent
            if isinstance(payload, dict):
                if any(k in payload for k in ("powerI", "current", "voltageI", "frequency")):
                    meta.setdefault("powerI", payload.get("powerI"))
                if "reservoir" in payload:
                    meta["reservoir"] = payload.get("reservoir")
            synth_outputs[name] = meta

        synth_modes = {m: {"mode": m, "name": m} for m in self._mode_commands}

        self._synth_config = {
            "Input": synth_inputs,
            "Output": synth_outputs,
            "Mode": synth_modes,
        }
        self._synth_keys = self._current_io_keys()

    # -- read surface (consumed by entity platforms) -------------

    async def async_resolve_collective_ids(self) -> None:  # pragma: no cover - no-op
        return

    async def async_refresh_collective_metadata(self) -> None:
        if self._client is None:
            return
        try:
            self._device_meta = await self._client.async_get_device()
        except HydrosApiError as err:
            self._note_error(err)

    async def async_get_collective_config(self, thing_id: str) -> dict[str, Any]:
        if not self._synth_config:
            self._build_synth_config()
        return self._synth_config

    def invalidate_collective_config(self, thing_id: str) -> None:
        self._metadata_dirty = True

    def get_collective_metadata(self, thing_id: str) -> dict[str, Any] | None:
        friendly = (
            self._device_meta.get("friendlyName")
            or self._entry.title
            or self._device_id
        )
        return {
            "friendlyName": friendly,
            "thingName": self._device_id,
            "thingType": self._device_meta.get("type"),
            "manufacturer": "Hydros",
            "serialNum": device_identifier(self._device_meta) or self._device_id,
        }

    def get_mode_options(self) -> list[str]:
        return list(self._mode_commands)

    def _input_payload(self, key: str) -> dict[str, Any] | None:
        inputs = self._status_payload.get("Input") or self._status_payload.get("input")
        if isinstance(inputs, dict):
            value = inputs.get(key)
            if isinstance(value, dict):
                return value
        return None

    def get_input_value(self, thing_id: str, input_key: str) -> Any:
        payload = self._input_payload(input_key)
        if payload is None:
            return None
        for candidate in ("value", "senseValue", "probeValue", "reading", "current", "rawValue"):
            if candidate in payload:
                return payload[candidate]
        return payload

    def get_input_metadata(self, thing_id: str, input_key: str) -> dict[str, Any] | None:
        return (self._synth_config.get("Input") or {}).get(input_key)

    def get_input_payload(self, thing_id: str, input_key: str) -> dict[str, Any] | None:
        return self._input_payload(input_key)

    def _output_payload(self, key: str) -> dict[str, Any] | None:
        outputs = self._status_payload.get("Output") or self._status_payload.get("output")
        if isinstance(outputs, dict):
            value = outputs.get(key)
            if isinstance(value, dict):
                return value
        return None

    def get_output_metadata(self, thing_id: str, output_key: str) -> dict[str, Any] | None:
        return (self._synth_config.get("Output") or {}).get(output_key)

    def get_output_payload(self, thing_id: str, output_key: str) -> dict[str, Any] | None:
        return self._output_payload(output_key)

    def get_output_value(self, thing_id: str, output_key: str) -> Any:
        payload = self._output_payload(output_key)
        if not isinstance(payload, dict):
            return payload
        if "valueState" in payload:
            return payload["valueState"]
        for key in ("powerI", "current", "voltageI", "frequency", "reservoir", "state"):
            if key in payload:
                return payload[key]
        return None

    def get_output_capabilities(self, thing_id: str, output_key: str) -> dict[str, bool]:
        om = self._override_meta.get(output_key)
        payload = self._output_payload(output_key) or {}
        otype = om.otype if om else None
        # These flags drive both read entities (binary_sensor / sensor) and
        # control entities, so they reflect the output's true shape. Control
        # entities are additionally gated on the "remote control" option, and a
        # read-only device key is enforced in _require_write().
        return {
            "is_doser": bool(om and "dose" in om.commands),
            "supports_binary_control": otype == "bool",
            "supports_percent_control": otype == "level",
            "has_power_metrics": any(
                k in payload for k in ("powerI", "current", "voltageI", "frequency")
            ),
            "has_reservoir": "reservoir" in payload,
        }

    def get_latest_status_ts(self, thing_id: str) -> datetime | None:
        return self._status_received

    def get_collective_status_payload(self, thing_id: str) -> dict[str, Any] | None:
        return self._status_payload or None

    def get_collective_message_count(self, thing_id: str) -> int:
        return self._message_count

    def is_collective_subscribed(self, thing_id: str) -> bool:
        return self._status_received is not None

    def get_api_health(self) -> dict[str, Any]:
        status = "unknown"
        if self._api_last_success is not None:
            status = "ok"
        if self._api_last_error_at and (
            self._api_last_success is None or self._api_last_error_at >= self._api_last_success
        ):
            status = "degraded"
        return {
            "status": status,
            "last_success": self._api_last_success,
            "last_error": self._api_last_error,
            "last_error_at": self._api_last_error_at,
        }

    def get_dosing_total(self, thing_id: str, output_name: str) -> float | None:
        return None

    def get_dosing_total_updated(self, thing_id: str, output_name: str) -> datetime | None:
        return None

    def get_debug_sample(self, thing_id: str) -> dict[str, Any] | None:
        return self._debug_sample

    async def async_collect_debug_sample(self, thing_id: str) -> None:
        self._debug_sample = {
            "collected": self._utcnow().isoformat(),
            "config": self._synth_config,
            "mqtt": self._status_payload,
        }

    async def async_refresh_dosing_logs(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        return

    async def async_subscribe_collective_status(self, thing_id: str) -> None:
        return

    async def async_force_status_from_api(self, thing_id: str) -> None:
        await self._async_poll()

    def signal_for_collective(self, thing_id: str) -> str:
        return SIGNAL_COLLECTIVE_UPDATED.format(entry=self._entry.entry_id, thing=thing_id)

    def signal_for_config(self, thing_id: str) -> str:
        return SIGNAL_CONFIG_UPDATED.format(entry=self._entry.entry_id, thing=thing_id)

    # -- command tracking --------------------------------------

    def _start_command(self, command_type: str, target_key: str, expected: Any) -> _Command:
        cmd = _Command(
            command_id=dt_util.utcnow().strftime("%Y%m%d%H%M%S%f"),
            command_type=command_type,
            target_key=target_key,
            expected_value=expected,
            issued_at=self._utcnow(),
        )
        self._commands[(command_type, target_key)] = cmd
        return cmd

    def _mark_from_result(self, cmd: _Command, result: dict[str, Any]) -> None:
        cmd.api_ack_at = self._utcnow()
        cmd.status = "api_acked"
        receipt = result.get("receipt") if isinstance(result, dict) else None
        if isinstance(receipt, dict) and receipt.get("applied") is True:
            cmd.status = "confirmed"
            cmd.confirmed_at = self._utcnow()

    def _mark_failed(self, cmd: _Command, err: Exception) -> None:
        cmd.status = "failed"
        cmd.error = str(err)
        cmd.api_ack_at = cmd.api_ack_at or self._utcnow()

    def _reconcile_commands(self, state: dict[str, Any]) -> None:
        now = self._utcnow()
        outputs = state.get("Output") or state.get("output") or {}
        for (ctype, target), cmd in list(self._commands.items()):
            if cmd.status in {"confirmed", "failed", "timed_out"}:
                continue
            if (now - cmd.issued_at).total_seconds() > DEFAULT_COMMAND_CONFIRM_TIMEOUT:
                cmd.status = "timed_out"
                continue
            if ctype == "mode":
                observed = state.get("mode")
                cmd.last_observed_value = observed
                if observed and str(observed).strip().lower() == str(cmd.expected_value).strip().lower():
                    cmd.status = "confirmed"
                    cmd.confirmed_at = now
                continue
            output_payload = outputs.get(target) if isinstance(outputs, dict) else None
            if not isinstance(output_payload, dict):
                continue
            observed = output_payload.get("valueState")
            cmd.last_observed_value = observed
            if _output_states_match(cmd.expected_value, observed):
                cmd.status = "confirmed"
                cmd.confirmed_at = now

    def get_command_status(
        self, thing_id: str, command_type: str, target_key: str
    ) -> dict[str, Any] | None:
        cmd = self._commands.get((command_type, target_key))
        if not cmd:
            return None
        if cmd.status in {"pending", "api_acked"}:
            if (self._utcnow() - cmd.issued_at).total_seconds() > DEFAULT_COMMAND_CONFIRM_TIMEOUT:
                cmd.status = "timed_out"
        return {
            "id": cmd.command_id,
            "status": cmd.status,
            "expected": cmd.expected_value,
            "observed": cmd.last_observed_value,
            "issued_at": cmd.issued_at.isoformat(),
            "api_ack_at": cmd.api_ack_at.isoformat() if cmd.api_ack_at else None,
            "confirmed_at": cmd.confirmed_at.isoformat() if cmd.confirmed_at else None,
            "error": cmd.error,
            "confirm_timeout_seconds": DEFAULT_COMMAND_CONFIRM_TIMEOUT,
        }

    def get_pending_command_count(self, thing_id: str) -> int:
        return sum(1 for c in self._commands.values() if c.status in {"pending", "api_acked"})

    # -- cooldowns --------------------------------------------

    def _enforce_output_cooldown(self, output_name: str) -> None:
        now = self._utcnow()
        last = self._last_output_command_at.get(output_name)
        if last is not None and (now - last).total_seconds() < DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS:
            raise HomeAssistantError(
                f"Output command rate-limited for {output_name}; wait "
                f"{DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS:.1f}s between commands"
            )
        self._last_output_command_at[output_name] = now

    def _enforce_mode_cooldown(self) -> None:
        now = self._utcnow()
        if (
            self._last_mode_command_at is not None
            and (now - self._last_mode_command_at).total_seconds()
            < DEFAULT_MODE_COMMAND_COOLDOWN_SECONDS
        ):
            raise HomeAssistantError(
                f"Mode command rate-limited; wait {DEFAULT_MODE_COMMAND_COOLDOWN_SECONDS:.1f}s "
                "between changes"
            )
        self._last_mode_command_at = now

    def _require_write(self) -> None:
        if not self._write_capable:
            raise HomeAssistantError(
                "This HYDROS device key is read-only. Create a read/write device key in the "
                "HYDROS app and reconfigure the integration to enable control."
            )
        if self._client is None:
            raise HomeAssistantError("Hydros API client is not ready")

    def _lookup_key(self, output_name: str) -> _OverrideMeta:
        om = self._override_meta.get(output_name)
        if om is None:
            raise HomeAssistantError(
                f"Output '{output_name}' is not overridable via the HYDROS Public API"
            )
        return om

    # -- control surface -------------------------------------

    async def async_change_mode(self, thing_id: str, mode: str) -> None:
        if not mode:
            return
        self._require_write()
        self._enforce_mode_cooldown()
        cmd = self._start_command("mode", "mode", mode)
        assert self._client is not None
        try:
            result = await self._client.async_send_command("mode", mode, receipt=True)
            self._note_success()
            self._mark_from_result(cmd, result)
        except HydrosApiError as err:
            self._note_error(err)
            self._mark_failed(cmd, err)
            raise HomeAssistantError(f"Hydros mode change failed: {err}") from err
        await self._async_poll()

    async def async_set_output_state(
        self, thing_id: str, output_name: str, state: int | str
    ) -> None:
        if not output_name:
            return
        self._require_write()
        self._enforce_output_cooldown(output_name)
        om = self._lookup_key(output_name)
        norm = _normalize_output_state(state)
        cmd = self._start_command("output", output_name, state)
        assert self._client is not None
        try:
            if norm == -1:
                result = await self._client.async_delete_override(om.key, receipt=True)
            elif om.otype == "bool":
                result = await self._client.async_put_overrides({om.key: bool(norm)}, receipt=True)
            else:
                level = _coerce_level(state, om)
                result = await self._client.async_put_overrides({om.key: level}, receipt=True)
            self._note_success()
            self._mark_from_result(cmd, result)
        except HydrosApiError as err:
            self._note_error(err)
            self._mark_failed(cmd, err)
            raise HomeAssistantError(f"Hydros output command failed: {err}") from err
        self._optimistic_output(output_name, norm)
        await self._async_poll()

    async def async_set_pump_speed(self, thing_id: str, output_name: str, percent: float) -> None:
        self._require_write()
        self._enforce_output_cooldown(output_name)
        om = self._lookup_key(output_name)
        speed = max(0.0, min(100.0, float(percent)))
        level = int(round(speed * 100.0))
        level = max(om.minimum, min(om.maximum, level))
        cmd = self._start_command("output", output_name, level)
        assert self._client is not None
        try:
            result = await self._client.async_put_overrides({om.key: level}, receipt=True)
            self._note_success()
            self._mark_from_result(cmd, result)
        except HydrosApiError as err:
            self._note_error(err)
            self._mark_failed(cmd, err)
            raise HomeAssistantError(f"Hydros pump speed command failed: {err}") from err
        self._optimistic_output(output_name, level)
        await self._async_poll()

    async def async_manual_dose(self, thing_id: str, output_name: str, amount_ml: float) -> None:
        if amount_ml <= 0:
            raise HomeAssistantError("amount_ml must be greater than 0")
        self._require_write()
        self._enforce_output_cooldown(output_name)
        om = self._lookup_key(output_name)
        if "dose" not in om.commands or om.dose_arg is None:
            raise HomeAssistantError(
                f"Output '{output_name}' does not expose a manual dose command"
            )
        # Dose command argument is in 0.1 mL units.
        value = int(round(float(amount_ml) * 10.0))
        lo, hi = om.dose_arg
        value = max(lo, min(hi, value))
        cmd = self._start_command("output", output_name, f"dose:{value}")
        assert self._client is not None
        try:
            result = await self._client.async_send_command(
                om.key, "dose", value=value, receipt=True
            )
            self._note_success()
            self._mark_from_result(cmd, result)
        except HydrosApiError as err:
            self._note_error(err)
            self._mark_failed(cmd, err)
            raise HomeAssistantError(f"Hydros manual dose failed: {err}") from err
        await self._async_poll()

    @callback
    def _optimistic_output(self, output_name: str, value: Any) -> None:
        outputs = self._status_payload.setdefault("Output", {})
        if not isinstance(outputs, dict):
            return
        payload = outputs.get(output_name)
        if not isinstance(payload, dict):
            payload = {}
            outputs[output_name] = payload
        if value == -1:
            payload["override"] = False
        elif isinstance(value, bool):
            payload["valueState"] = _LEVEL_MAX if value else 0
            payload["override"] = True
        elif isinstance(value, (int, float)):
            if value in (0, 1):
                payload["valueState"] = _LEVEL_MAX if value == 1 else 0
            else:
                payload["valueState"] = int(value)
            payload["override"] = True
        self._status_received = dt_util.utcnow()
        self._dispatch()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_output_state(value: Any) -> int:
    """Coerce an on/off/auto-ish request to an int.

    ``"on"``/``"off"``/``"auto"`` map to ``1``/``0``/``-1``. Any other numeric
    value passes straight through (including negative levels for reversible
    outputs) so it is *not* mistaken for an "auto" request.
    """
    if isinstance(value, str):
        mapped = _OUTPUT_STATE_ALIASES.get(value.strip().lower())
        if mapped is not None:
            return mapped
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_level(value: Any, om: _OverrideMeta) -> int:
    """Resolve a level-output override value, clamped to the metadata range."""
    if isinstance(value, str):
        alias = _OUTPUT_STATE_ALIASES.get(value.strip().lower())
        if alias == 1:
            return om.maximum
        if alias == 0:
            return max(om.minimum, 0)
    try:
        num = int(round(float(value)))
    except (TypeError, ValueError):
        return max(om.minimum, 0)
    return max(om.minimum, min(om.maximum, num))


def _output_states_match(expected: Any, observed: Any) -> bool:
    exp = _normalize_output_state(expected)
    try:
        obs = int(observed)
    except (TypeError, ValueError):
        return str(expected).strip().lower() == str(observed).strip().lower()
    if exp == 1:
        return obs > 0
    if exp == 0:
        return obs == 0
    if exp == -1:
        return True  # returned to auto; any scheduled value is acceptable
    return abs(obs - exp) <= 1


def _classify_input(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort sensor typing from the input name + which value field it reports.

    The Public API state document carries no ``senseMode``/``probeMode``, so this
    is heuristic. Unrecognised inputs become plain numeric sensors.
    """
    n = name.strip().lower()
    has_probe = "probeValue" in payload or "probeRawValue" in payload

    if "temp" in n:
        return {"senseMode": "temp"}
    if n == "ph" or n.startswith("ph ") or n.endswith(" ph") or "ph probe" in n:
        return {"type": "probe", "probeMode": 1}
    if "orp" in n:
        return {"type": "probe", "probeMode": 2}
    if "alk" in n or "dkh" in n:
        return {"type": "probe", "probeMode": 3}
    if "salinity" in n:
        return {"senseMode": "salinity"}
    if "conductivit" in n:
        return {"senseMode": "conductivity"}
    if "tds" in n:
        return {"senseMode": "tds"}
    if "flow" in n:
        return {"senseMode": "flowrate"}
    if "level" in n or "float" in n:
        return {"senseMode": "triplelevel"}
    if has_probe:
        return {"type": "probe", "probeMode": 0}
    return {}


def _merge_payloads(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if not base:
        return dict(incoming)
    merged = dict(base)
    for key, value in incoming.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            child = _merge_payloads(current, value)
            if "alert" in current and "alert" not in value:
                child.pop("alert", None)
            merged[key] = child
        else:
            merged[key] = value
    return merged
