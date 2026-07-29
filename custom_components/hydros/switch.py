from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    CONF_ENABLE_REMOTE_CONTROL,
    DEFAULT_AVAILABILITY_WINDOW_SECONDS,
    DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS,
    DOMAIN,
)
from .entity_builders import build_output_display_name
from .hydros_hub import HydrosHub
from .sensor import OUTPUT_STATE_ALIASES, _coerce_int, _map_output_state_label

_LOGGER = logging.getLogger(__name__)


@dataclass
class HydrosOutputSwitchDescription(SwitchEntityDescription):
    thing_id: str | None = None
    output_key: str | None = None


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
            "Hydros remote control disabled for entry %s; output switch entities are hidden",
            entry.entry_id,
        )
        registry = er.async_get(hass)
        for registry_entry in list(registry.entities.values()):
            if registry_entry.config_entry_id != entry.entry_id:
                continue
            if registry_entry.platform != DOMAIN:
                continue
            unique_id = registry_entry.unique_id or ""
            if unique_id.endswith("-output-switch"):
                registry.async_remove(registry_entry.entity_id)
        return

    entry_data = hass.data[DOMAIN][entry.entry_id]
    if isinstance(entry_data, HydrosHub):
        entry_data = {"hub": entry_data}
        hass.data[DOMAIN][entry.entry_id] = entry_data

    hub: HydrosHub = entry_data["hub"]

    entities: list[HydrosOutputSwitch] = []

    for thing_id in hub.collective_ids:
        try:
            config = await hub.async_get_collective_config(thing_id)
        except Exception as err:
            _LOGGER.warning("Hydros failed to load switch config for %s: %s", thing_id, err)
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
            capabilities = hub.get_output_capabilities(thing_id, output_key)
            if not capabilities.get("supports_binary_control"):
                continue
            if capabilities.get("supports_percent_control"):
                continue

            # Skip outputs that support auto mode (they'll be handled by outlet selects)
            # AUTO outputs have temperature/threshold metadata like onTemp, offTemp, fallback, outputDevice
            supports_auto = any(
                key in output_meta 
                for key in ("onTemp", "offTemp", "fallback", "outputDevice", "autoControl")
            )
            
            if supports_auto:
                continue

            name = build_output_display_name(output_meta, output_key)
            slug = slugify(f"{thing_id}-output-switch-{output_key}")

            description = HydrosOutputSwitchDescription(
                key=f"{entry.entry_id}-{thing_id}-{slug}",
                name=name,
                thing_id=thing_id,
                output_key=output_key,
            )

            entities.append(
                HydrosOutputSwitch(
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


class HydrosOutputSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        *,
        hub: HydrosHub,
        description: HydrosOutputSwitchDescription,
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
        return delta <= DEFAULT_AVAILABILITY_WINDOW_SECONDS

    @property
    def is_on(self) -> bool | None:
        if not self._thing_id or not self._output_key:
            return None

        payload = self._hub.get_output_payload(self._thing_id, self._output_key) or {}
        metadata = self._hub.get_output_metadata(self._thing_id, self._output_key) or {}

        value_state = payload.get("valueState")
        numeric_state = _coerce_int(value_state)
        if numeric_state is None and isinstance(value_state, str):
            alias = OUTPUT_STATE_ALIASES.get(value_state.strip().lower())
            if alias is not None:
                numeric_state = alias

        if numeric_state is not None:
            if numeric_state <= 0:
                return False
            if numeric_state > 0:
                return True

        label = _map_output_state_label(payload, metadata)
        if label == "on":
            return True
        if label == "off":
            return False

        if numeric_state is not None:
            return bool(numeric_state)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        payload = self._hub.get_output_payload(self._thing_id, self._output_key) or {}
        metadata = self._hub.get_output_metadata(self._thing_id, self._output_key) or {}

        attrs: dict[str, Any] = {
            "thing_id": self._thing_id,
            "output_key": self._output_key,
        }

        label = _map_output_state_label(payload, metadata)
        if label:
            attrs["state_label"] = label

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._hub.async_set_output_state(self._thing_id, self._output_key, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.async_set_output_state(self._thing_id, self._output_key, 0)

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
