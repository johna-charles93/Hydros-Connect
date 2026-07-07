from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ENABLE_REMOTE_CONTROL,
    DOMAIN,
    PLATFORMS,
    SERVICE_CHANGE_MODE,
    SERVICE_MANUAL_DOSE,
    SERVICE_SET_OUTPUT_STATE,
    SERVICE_SET_PUMP_SPEED,
)
from .hydros_hub import HydrosHub

ATTR_THING_ID = "thing_id"
ATTR_OUTPUT_KEY = "output_key"
ATTR_STATE = "state"
ATTR_PERCENT = "percent"
ATTR_MODE = "mode"
ATTR_AMOUNT_ML = "amount_ml"


def _is_remote_control_enabled(entry: ConfigEntry) -> bool:
    return bool(
        entry.options.get(
            CONF_ENABLE_REMOTE_CONTROL,
            entry.data.get(CONF_ENABLE_REMOTE_CONTROL, False),
        )
    )


def _find_hub_for_thing(hass: HomeAssistant, thing_id: str) -> tuple[ConfigEntry, HydrosHub] | None:
    domain_data = hass.data.get(DOMAIN, {})
    for entry_id, entry_data in domain_data.items():
        if not isinstance(entry_data, dict):
            continue
        hub = entry_data.get("hub")
        if not isinstance(hub, HydrosHub):
            continue
        if thing_id in hub.collective_ids:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                continue
            return entry, hub
    return None


def _ensure_services_registered(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_OUTPUT_STATE):
        return

    async def _handle_set_output_state(call: ServiceCall) -> None:
        thing_id = str(call.data[ATTR_THING_ID]).strip()
        output_key = str(call.data[ATTR_OUTPUT_KEY]).strip()
        state = call.data[ATTR_STATE]

        result = _find_hub_for_thing(hass, thing_id)
        if result is None:
            raise HomeAssistantError(f"Unknown Hydros thing_id: {thing_id}")
        entry, hub = result
        if not _is_remote_control_enabled(entry):
            raise HomeAssistantError("Remote control is disabled for this Hydros entry")

        await hub.async_set_output_state(thing_id, output_key, state)

    async def _handle_set_pump_speed(call: ServiceCall) -> None:
        thing_id = str(call.data[ATTR_THING_ID]).strip()
        output_key = str(call.data[ATTR_OUTPUT_KEY]).strip()
        percent = float(call.data[ATTR_PERCENT])

        result = _find_hub_for_thing(hass, thing_id)
        if result is None:
            raise HomeAssistantError(f"Unknown Hydros thing_id: {thing_id}")
        entry, hub = result
        if not _is_remote_control_enabled(entry):
            raise HomeAssistantError("Remote control is disabled for this Hydros entry")

        await hub.async_set_pump_speed(thing_id, output_key, percent)

    async def _handle_change_mode(call: ServiceCall) -> None:
        thing_id = str(call.data[ATTR_THING_ID]).strip()
        mode = str(call.data[ATTR_MODE]).strip()

        result = _find_hub_for_thing(hass, thing_id)
        if result is None:
            raise HomeAssistantError(f"Unknown Hydros thing_id: {thing_id}")
        entry, hub = result
        if not _is_remote_control_enabled(entry):
            raise HomeAssistantError("Remote control is disabled for this Hydros entry")

        await hub.async_change_mode(thing_id, mode)

    async def _handle_manual_dose(call: ServiceCall) -> None:
        thing_id = str(call.data[ATTR_THING_ID]).strip()
        output_key = str(call.data[ATTR_OUTPUT_KEY]).strip()
        amount_ml = float(call.data[ATTR_AMOUNT_ML])

        result = _find_hub_for_thing(hass, thing_id)
        if result is None:
            raise HomeAssistantError(f"Unknown Hydros thing_id: {thing_id}")
        entry, hub = result
        if not _is_remote_control_enabled(entry):
            raise HomeAssistantError("Remote control is disabled for this Hydros entry")

        await hub.async_manual_dose(thing_id, output_key, amount_ml)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OUTPUT_STATE,
        _handle_set_output_state,
        schema=vol.Schema(
            {
                vol.Required(ATTR_THING_ID): cv.string,
                vol.Required(ATTR_OUTPUT_KEY): cv.string,
                vol.Required(ATTR_STATE): vol.Any(cv.string, vol.Coerce(int)),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PUMP_SPEED,
        _handle_set_pump_speed,
        schema=vol.Schema(
            {
                vol.Required(ATTR_THING_ID): cv.string,
                vol.Required(ATTR_OUTPUT_KEY): cv.string,
                vol.Required(ATTR_PERCENT): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHANGE_MODE,
        _handle_change_mode,
        schema=vol.Schema(
            {
                vol.Required(ATTR_THING_ID): cv.string,
                vol.Required(ATTR_MODE): cv.string,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_MANUAL_DOSE,
        _handle_manual_dose,
        schema=vol.Schema(
            {
                vol.Required(ATTR_THING_ID): cv.string,
                vol.Required(ATTR_OUTPUT_KEY): cv.string,
                vol.Required(ATTR_AMOUNT_ML): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
            }
        ),
    )


def _maybe_unregister_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    for entry_data in domain_data.values():
        if isinstance(entry_data, dict) and isinstance(entry_data.get("hub"), HydrosHub):
            return
    for service_name in (
        SERVICE_SET_OUTPUT_STATE,
        SERVICE_SET_PUMP_SPEED,
        SERVICE_CHANGE_MODE,
        SERVICE_MANUAL_DOSE,
    ):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = HydrosHub(hass, entry)
    await hub.async_setup()

    domain_data = hass.data.setdefault(DOMAIN, {})
    entry_data = {"hub": hub}
    domain_data[entry.entry_id] = entry_data
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    _ensure_services_registered(hass)

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = True
    if PLATFORMS:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    domain_data = hass.data.get(DOMAIN)
    entry_data: dict[str, Any] | None = None
    if domain_data is not None:
        entry_data = domain_data.pop(entry.entry_id, None)

    sensor_manager = None
    binary_manager = None
    hub: HydrosHub | None = None
    if entry_data:
        sensor_manager = entry_data.get("sensor_manager")
        binary_manager = entry_data.get("binary_sensor_manager")
        hub = entry_data.get("hub")

    if sensor_manager:
        await sensor_manager.async_unload()

    if binary_manager:
        await binary_manager.async_unload()

    if hub:
        await hub.async_unload()

    if domain_data is not None and not domain_data:
        _maybe_unregister_services(hass)
        hass.data.pop(DOMAIN, None)
    else:
        _maybe_unregister_services(hass)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
