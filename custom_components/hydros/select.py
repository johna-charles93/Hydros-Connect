from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_REMOTE_CONTROL,
    DEFAULT_MODE_COMMAND_COOLDOWN_SECONDS,
    DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS,
    DOMAIN,
)
from .entity_builders import build_output_display_name
from .hydros_hub import HydrosHub

_LOGGER = logging.getLogger(__name__)


@dataclass
class HydrosModeSelectEntityDescription(SelectEntityDescription):
    thing_id: str | None = None


@dataclass
class HydrosOutputSelectDescription(SelectEntityDescription):
    thing_id: str | None = None
    output_key: str | None = None


def _extract_modes_from_config(
    config: dict[str, Any] | None,
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    options: list[str] = []
    option_to_mode: dict[str, str] = {}
    value_to_option: dict[str, str] = {}

    if not isinstance(config, dict):
        return options, option_to_mode, value_to_option

    def _iter_mode_items(source: Any) -> list[tuple[Any, Any]]:
        if isinstance(source, dict):
            return list(source.items())
        if isinstance(source, list):
            return [(idx, item) for idx, item in enumerate(source)]
        return []

    mode_sources: list[Any] = []
    for key in ("Mode", "mode", "Modes", "modes"):
        if key in config:
            mode_sources.append(config.get(key))

    option_block = config.get("Option")
    if isinstance(option_block, dict):
        for key, value in option_block.items():
            if "mode" not in str(key).lower():
                continue
            if isinstance(value, (dict, list)):
                mode_sources.append(value)

    for mode_source in mode_sources:
        for mode_key, mode_meta in _iter_mode_items(mode_source):
            mode_id = str(mode_key).strip()
            if not mode_id and not isinstance(mode_meta, dict):
                continue

            option: str | None = None
            if isinstance(mode_meta, dict):
                if bool(mode_meta.get("invisible") or mode_meta.get("hidden")):
                    continue
                mode_id = str(
                    mode_meta.get("mode")
                    or mode_meta.get("id")
                    or mode_meta.get("modeId")
                    or mode_meta.get("modeID")
                    or mode_meta.get("value")
                    or mode_meta.get("key")
                    or mode_id
                ).strip() or str(mode_key).strip()
                option = (
                    str(
                        mode_meta.get("friendlyName")
                        or mode_meta.get("name")
                        or mode_meta.get("label")
                        or mode_meta.get("modeName")
                        or mode_meta.get("title")
                        or mode_meta.get("text")
                        or mode_id
                    )
                    .strip()
                    or mode_id
                )
            else:
                option = str(mode_meta).strip() or mode_id

            if not mode_id or not option:
                continue

            if option not in options:
                options.append(option)
            option_to_mode[option] = mode_id

            value_to_option[mode_id] = option
            value_to_option[option] = option
            value_to_option[mode_id.lower()] = option
            value_to_option[option.lower()] = option

    return options, option_to_mode, value_to_option


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    remote_control_enabled = bool(
        entry.options.get(
            CONF_ENABLE_REMOTE_CONTROL,
            entry.data.get(CONF_ENABLE_REMOTE_CONTROL, False),
        )
    )
    if not remote_control_enabled:
        _LOGGER.debug(
            "Hydros remote control disabled for entry %s; mode select entities are hidden",
            entry.entry_id,
        )
        registry = er.async_get(hass)
        for registry_entry in list(registry.entities.values()):
            if registry_entry.config_entry_id != entry.entry_id:
                continue
            if registry_entry.platform != DOMAIN:
                continue
            unique_id = registry_entry.unique_id or ""
            if unique_id.endswith("-mode-select"):
                registry.async_remove(registry_entry.entity_id)
        return

    entry_data = hass.data[DOMAIN][entry.entry_id]
    if isinstance(entry_data, HydrosHub):
        entry_data = {"hub": entry_data}
        hass.data[DOMAIN][entry.entry_id] = entry_data

    hub: HydrosHub = entry_data["hub"]

    entities: list[HydrosModeSelect] = []
    for thing_id in hub.collective_ids:
        metadata = hub.get_collective_metadata(thing_id) or {}
        device_name = metadata.get("friendlyName") or metadata.get("thingName") or thing_id
        manufacturer = metadata.get("manufacturer") or "Hydros"
        model = metadata.get("thingType") or metadata.get("type")
        description = HydrosModeSelectEntityDescription(
            key=f"{entry.entry_id}-{thing_id}-mode-select",
            name=f"{device_name} Mode Select",
            thing_id=thing_id,
        )
        entities.append(
            HydrosModeSelect(
                hub=hub,
                description=description,
                device_info=DeviceInfo(
                    identifiers={(DOMAIN, thing_id)},
                    name=device_name,
                    manufacturer=manufacturer,
                    model=model,
                ),
            )
        )

    if entities:
        async_add_entities(entities)

    # Add outlet select entities for outputs that support on/off/auto
    outlet_entities: list[HydrosOutputSelect] = []
    for thing_id in hub.collective_ids:
        try:
            config = await hub.async_get_collective_config(thing_id)
        except Exception as err:
            _LOGGER.warning("Hydros failed to load outlet select config for %s: %s", thing_id, err)
            continue

        metadata = hub.get_collective_metadata(thing_id) or {}
        device_name = metadata.get("friendlyName") or metadata.get("thingName") or thing_id
        manufacturer = metadata.get("manufacturer") or "Hydros"
        model = metadata.get("thingType") or metadata.get("type")

        outputs = config.get("Output")
        if not isinstance(outputs, dict):
            continue

        for output_key, output_meta in outputs.items():
            if not isinstance(output_meta, dict):
                continue

            # Check if this output supports binary control and can have auto mode
            capabilities = hub.get_output_capabilities(thing_id, output_key)
            if not capabilities.get("supports_binary_control"):
                continue
            if capabilities.get("supports_percent_control"):
                continue

            # Check if the output metadata indicates auto mode support
            # AUTO outputs have temperature/threshold metadata like onTemp, offTemp, fallback, outputDevice
            supports_auto = any(
                key in output_meta 
                for key in ("onTemp", "offTemp", "fallback", "outputDevice", "autoControl")
            )
            
            if not supports_auto:
                continue

            name = build_output_display_name(output_meta, output_key)
            slug = f"{thing_id}-output-select-{output_key}"

            description = HydrosOutputSelectDescription(
                key=f"{entry.entry_id}-{slug}",
                name=name,
                thing_id=thing_id,
                output_key=output_key,
            )

            outlet_entities.append(
                HydrosOutputSelect(
                    hub=hub,
                    description=description,
                    device_info=DeviceInfo(
                        identifiers={(DOMAIN, thing_id)},
                        name=device_name,
                        manufacturer=manufacturer,
                        model=model,
                    ),
                )
            )

    if outlet_entities:
        async_add_entities(outlet_entities)


class HydrosModeSelect(SelectEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        hub: HydrosHub,
        description: HydrosModeSelectEntityDescription,
        device_info: DeviceInfo,
    ) -> None:
        self._hub = hub
        self.entity_description = description
        self._device_info = device_info
        self._thing_id = description.thing_id or ""
        self._attr_unique_id = description.key
        self._attr_name = "Mode"
        self._attr_options: list[str] = []
        self._option_to_mode: dict[str, str] = {}
        self._value_to_option: dict[str, str] = {}
        self._remove_dispatchers: list[Callable[[], None]] = []

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    @property
    def available(self) -> bool:
        if not self._thing_id:
            return False
        last_ts = self._hub.get_latest_status_ts(self._thing_id)
        if not last_ts:
            return False
        delta = (datetime.now(timezone.utc) - last_ts).total_seconds()
        return delta <= 30

    @property
    def current_option(self) -> str | None:
        payload = self._hub.get_collective_status_payload(self._thing_id) or {}
        mode = payload.get("mode")
        if mode is None:
            return None

        mode_str = str(mode).strip()
        if not mode_str:
            return None

        option = self._value_to_option.get(mode_str)
        if option is not None:
            return option

        option = self._value_to_option.get(mode_str.lower())
        if option is not None:
            return option

        if mode_str in self.options:
            return mode_str

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs: dict[str, Any] = {
            "thing_id": self._thing_id,
            "command_cooldown_seconds": DEFAULT_MODE_COMMAND_COOLDOWN_SECONDS,
        }
        command_status = self._hub.get_command_status(
            self._thing_id,
            "mode",
            "mode",
        )
        if command_status:
            attrs["last_command"] = command_status
        if self._option_to_mode:
            attrs["option_to_mode"] = self._option_to_mode
        return attrs

    async def async_select_option(self, option: str) -> None:
        mode_value = self._option_to_mode.get(option, option)
        try:
            await self._hub.async_change_mode(self._thing_id, mode_value)
        except Exception:
            # The command failed (e.g. deleted mode, verification mismatch).
            # Fetch the authoritative status from the REST API (bypasses
            # MQTT entirely) so the entity reflects the real current mode.
            await self._async_refresh_options(force=True)
            try:
                await self._hub.async_force_status_from_api(self._thing_id)
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "API status refresh failed for %s", self._thing_id
                )
            raise

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        self._remove_dispatchers.append(
            async_dispatcher_connect(
                self.hass,
                self._hub.signal_for_collective(self._thing_id),
                self._handle_collective_signal,
            )
        )
        self._remove_dispatchers.append(
            async_dispatcher_connect(
                self.hass,
                self._hub.signal_for_config(self._thing_id),
                self._handle_config_signal,
            )
        )

        if self._thing_id:
            await self._hub.async_subscribe_collective_status(self._thing_id)

        await self._async_refresh_options()

    async def async_will_remove_from_hass(self) -> None:
        for unsub in self._remove_dispatchers:
            unsub()
        self._remove_dispatchers.clear()
        await super().async_will_remove_from_hass()

    def _handle_collective_signal(self, _: str) -> None:
        self.schedule_update_ha_state()

    def _handle_config_signal(self, _: str) -> None:
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_refresh_options(),
        )

    async def _async_refresh_options(self, force: bool = False) -> None:
        if not self._thing_id:
            return
        if force:
            self._hub.invalidate_collective_config(self._thing_id)
        try:
            config = await self._hub.async_get_collective_config(self._thing_id)
        except Exception as err:
            _LOGGER.debug("Unable to refresh Hydros modes for %s: %s", self._thing_id, err)
            return

        options, option_to_mode, value_to_option = _extract_modes_from_config(config)
        changed = (
            options != self._attr_options
            or option_to_mode != self._option_to_mode
            or value_to_option != self._value_to_option
        )

        self._attr_options = options
        self._option_to_mode = option_to_mode
        self._value_to_option = value_to_option

        if changed:
            self.async_write_ha_state()


class HydrosOutputSelect(SelectEntity):
    """Select entity for Hydros outputs that support on/off/auto modes."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_options = ["off", "on", "auto"]

    # Map option display names to numeric values
    _OPTION_TO_VALUE = {
        "off": 0,
        "on": 1,
        "auto": -1,
    }

    # Map numeric values to option display names
    _VALUE_TO_OPTION = {
        0: "off",
        1: "on",
        -1: "auto",
    }

    def __init__(
        self,
        *,
        hub: HydrosHub,
        description: HydrosOutputSelectDescription,
        device_info: DeviceInfo,
    ) -> None:
        self._hub = hub
        self.entity_description = description
        self._device_info = device_info
        self._thing_id = description.thing_id or ""
        self._output_key = description.output_key or ""
        self._attr_unique_id = description.key
        self._attr_name = description.name
        self._remove_dispatcher: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    @property
    def available(self) -> bool:
        if not self._thing_id:
            return False
        last_ts = self._hub.get_latest_status_ts(self._thing_id)
        if not last_ts:
            return False
        delta = (datetime.now(timezone.utc) - last_ts).total_seconds()
        return delta <= 30

    @property
    def current_option(self) -> str | None:
        if not self._thing_id or not self._output_key:
            return None

        payload = self._hub.get_output_payload(self._thing_id, self._output_key) or {}
        
        # Check override flag to determine if in AUTO mode
        # override: false = AUTO mode (Hydros controller in auto)
        # override: true = Manual ON/OFF mode
        override = payload.get("override")
        if override is False:
            return "auto"
        
        # If override is true or not present, check valueState for on/off
        value_state = payload.get("valueState")

        # Try numeric value first
        try:
            numeric_value = int(value_state)
            if numeric_value in self._VALUE_TO_OPTION:
                return self._VALUE_TO_OPTION[numeric_value]
        except (TypeError, ValueError):
            pass

        # Try string value
        if isinstance(value_state, str):
            normalized = value_state.strip().lower()
            if normalized in self._OPTION_TO_VALUE:
                return normalized

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        payload = self._hub.get_output_payload(self._thing_id, self._output_key) or {}

        attrs: dict[str, Any] = {
            "thing_id": self._thing_id,
            "output_key": self._output_key,
        }

        command_status = self._hub.get_command_status(
            self._thing_id,
            "output",
            self._output_key,
        )
        if command_status:
            attrs["last_command"] = command_status

        attrs["command_cooldown_seconds"] = DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS

        if payload:
            attrs["payload"] = payload

        return attrs

    async def async_select_option(self, option: str) -> None:
        if option not in self._OPTION_TO_VALUE:
            raise ValueError(f"Invalid option: {option}")

        value = self._OPTION_TO_VALUE[option]
        await self._hub.async_set_output_state(self._thing_id, self._output_key, value)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_dispatcher = async_dispatcher_connect(
            self.hass,
            self._hub.signal_for_collective(self._thing_id),
            self._handle_signal,
        )
        if self._thing_id:
            await self._hub.async_subscribe_collective_status(self._thing_id)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_dispatcher:
            self._remove_dispatcher()
            self._remove_dispatcher = None
        await super().async_will_remove_from_hass()

    def _handle_signal(self, _: str) -> None:
        self.schedule_update_ha_state()

