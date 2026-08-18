from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

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
ATTR_ENTITY_ID = "entity_id"


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


def _find_hub_for_entity(
    hass: HomeAssistant,
    entity_id: str,
) -> tuple[ConfigEntry, HydrosHub, str | None, str | None] | None:
    registry = er.async_get(hass)
    registry_entry = registry.async_get(entity_id)
    if registry_entry is None or registry_entry.config_entry_id is None:
        return None

    entry = hass.config_entries.async_get_entry(registry_entry.config_entry_id)
    if entry is None:
        return None

    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(registry_entry.config_entry_id)
    if not isinstance(entry_data, dict):
        return None

    hub = entry_data.get("hub")
    if not isinstance(hub, HydrosHub):
        return None

    state = hass.states.get(entity_id)
    attrs = {} if state is None else state.attributes
    thing_id = attrs.get(ATTR_THING_ID)
    output_key = attrs.get(ATTR_OUTPUT_KEY)
    if isinstance(thing_id, str):
        thing_id = thing_id.strip() or None
    else:
        thing_id = None
    if isinstance(output_key, str):
        output_key = output_key.strip() or None
    else:
        output_key = None

    return entry, hub, thing_id, output_key


def _resolve_thing_and_output(
    hass: HomeAssistant,
    call: ServiceCall,
    *,
    require_output: bool,
) -> tuple[ConfigEntry, HydrosHub, str, str | None]:
    entity_id = call.data.get(ATTR_ENTITY_ID)
    if isinstance(entity_id, str) and entity_id.strip():
        resolved = _find_hub_for_entity(hass, entity_id.strip())
        if resolved is None:
            raise HomeAssistantError(f"Unknown or unmanaged Hydros entity_id: {entity_id}")
        entry, hub, thing_id, output_key = resolved
        if not _is_remote_control_enabled(entry):
            raise HomeAssistantError("Remote control is disabled for this Hydros entry")
        if not thing_id:
            raise HomeAssistantError(
                f"Entity {entity_id} is missing '{ATTR_THING_ID}' attribute required for control"
            )
        if require_output and not output_key:
            raise HomeAssistantError(
                f"Entity {entity_id} is missing '{ATTR_OUTPUT_KEY}' attribute required for output control"
            )
        return entry, hub, thing_id, output_key

    thing_id = str(call.data.get(ATTR_THING_ID, "")).strip()
    output_key = str(call.data.get(ATTR_OUTPUT_KEY, "")).strip()
    if not thing_id:
        raise HomeAssistantError(
            f"Provide either '{ATTR_ENTITY_ID}' or '{ATTR_THING_ID}'"
        )
    if require_output and not output_key:
        raise HomeAssistantError(
            f"Provide either '{ATTR_ENTITY_ID}' or '{ATTR_OUTPUT_KEY}'"
        )

    result = _find_hub_for_thing(hass, thing_id)
    if result is None:
        raise HomeAssistantError(f"Unknown Hydros thing_id: {thing_id}")
    entry, hub = result
    if not _is_remote_control_enabled(entry):
        raise HomeAssistantError("Remote control is disabled for this Hydros entry")

    return entry, hub, thing_id, output_key or None


def _ensure_services_registered(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_OUTPUT_STATE):
        return

    async def _handle_set_output_state(call: ServiceCall) -> None:
        _, hub, thing_id, output_key = _resolve_thing_and_output(hass, call, require_output=True)
        state = call.data[ATTR_STATE]
        assert output_key is not None
        await hub.async_set_output_state(thing_id, output_key, state)

    async def _handle_set_pump_speed(call: ServiceCall) -> None:
        _, hub, thing_id, output_key = _resolve_thing_and_output(hass, call, require_output=True)
        percent = float(call.data[ATTR_PERCENT])
        assert output_key is not None
        await hub.async_set_pump_speed(thing_id, output_key, percent)

    async def _handle_change_mode(call: ServiceCall) -> None:
        _, hub, thing_id, _ = _resolve_thing_and_output(hass, call, require_output=False)
        mode = str(call.data[ATTR_MODE]).strip()
        await hub.async_change_mode(thing_id, mode)

    async def _handle_manual_dose(call: ServiceCall) -> None:
        _, hub, thing_id, output_key = _resolve_thing_and_output(hass, call, require_output=True)
        amount_ml = float(call.data[ATTR_AMOUNT_ML])
        assert output_key is not None
        await hub.async_manual_dose(thing_id, output_key, amount_ml)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OUTPUT_STATE,
        _handle_set_output_state,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
                vol.Optional(ATTR_THING_ID): cv.string,
                vol.Optional(ATTR_OUTPUT_KEY): cv.string,
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
                vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
                vol.Optional(ATTR_THING_ID): cv.string,
                vol.Optional(ATTR_OUTPUT_KEY): cv.string,
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
                vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
                vol.Optional(ATTR_THING_ID): cv.string,
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
                vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
                vol.Optional(ATTR_THING_ID): cv.string,
                vol.Optional(ATTR_OUTPUT_KEY): cv.string,
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

    # Migration: remove legacy output-switch entities for outputs that now have
    # output-select entities. Build the set of output keys that have a select entry,
    # then prune any switch entries for the same key.
    registry = er.async_get(hass)
    select_output_keys: set[str] = set()
    for reg_entry in registry.entities.values():
        if reg_entry.config_entry_id != entry.entry_id:
            continue
        if reg_entry.platform != DOMAIN:
            continue
        uid = reg_entry.unique_id or ""
        if "-output-select-" in uid:
            select_output_keys.add(uid.split("-output-select-", 1)[-1])

    for reg_entry in list(registry.entities.values()):
        if reg_entry.config_entry_id != entry.entry_id:
            continue
        if reg_entry.platform != DOMAIN:
            continue
        uid = reg_entry.unique_id or ""
        if "-output-switch-" in uid:
            output_key = uid.split("-output-switch-", 1)[-1]
            if output_key in select_output_keys:
                registry.async_remove(reg_entry.entity_id)

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
    scene_return_manager = None
    hub: HydrosHub | None = None
    if entry_data:
        sensor_manager = entry_data.get("sensor_manager")
        binary_manager = entry_data.get("binary_sensor_manager")
        scene_return_manager = entry_data.get("scene_return_manager")
        hub = entry_data.get("hub")

    if sensor_manager:
        await sensor_manager.async_unload()

    if binary_manager:
        await binary_manager.async_unload()

    if scene_return_manager:
        await scene_return_manager.async_shutdown()

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
