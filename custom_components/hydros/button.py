from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    CONF_ALEXA_CUSTOM_SCENE_MODE,
    CONF_ALEXA_CUSTOM_SCENE_NAME,
    CONF_ALEXA_FEED_SCENE_MODE,
    CONF_ALEXA_FEED_SCENE_NAME,
    CONF_ALEXA_MAINT_SCENE_MODE,
    CONF_ALEXA_MAINT_SCENE_NAME,
    CONF_ALEXA_TARGET_COLLECTIVE,
    CONF_ENABLE_ALEXA_SCENES,
    CONF_ENABLE_REMOTE_CONTROL,
    DOMAIN,
)
from .hydros_hub import HydrosHub
from .mode_utils import extract_mode_options

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    if isinstance(entry_data, HydrosHub):
        entry_data = {"hub": entry_data}
        hass.data[DOMAIN][entry.entry_id] = entry_data

    hub: HydrosHub = entry_data["hub"]

    entities: list[ButtonEntity] = []
    for thing_id in hub.collective_ids:
        metadata = hub.get_collective_metadata(thing_id) or {}
        device_name = metadata.get("friendlyName") or metadata.get("thingName") or thing_id
        manufacturer = metadata.get("manufacturer") or "Hydros"
        model = metadata.get("thingType") or metadata.get("type")
        entities.append(
            HydrosDebugButton(
                hub=hub,
                thing_id=thing_id,
                device_info=DeviceInfo(
                    identifiers={(DOMAIN, thing_id)},
                    name=device_name,
                    manufacturer=manufacturer,
                    model=model,
                ),
            )
        )

        entities.append(
            HydrosSetupValidationButton(
                hub=hub,
                entry=entry,
                thing_id=thing_id,
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


class HydrosDebugButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, *, hub: HydrosHub, thing_id: str, device_info: DeviceInfo) -> None:
        self._hub = hub
        self._thing_id = thing_id
        self._device_info = device_info
        slug = slugify(f"{thing_id}-debug-sample")
        self._attr_unique_id = f"{hub.entry_id}-{thing_id}-{slug}"
        self._attr_name = "Debug Sample"

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    async def async_press(self) -> None:
        _LOGGER.debug("Hydros debug sample requested for %s", self._thing_id)
        await self._hub.async_collect_debug_sample(self._thing_id)


class HydrosSetupValidationButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        hub: HydrosHub,
        entry: ConfigEntry,
        thing_id: str,
        device_info: DeviceInfo,
    ) -> None:
        self._hub = hub
        self._entry = entry
        self._thing_id = thing_id
        self._device_info = device_info
        slug = slugify(f"{thing_id}-setup-validation")
        self._attr_unique_id = f"{hub.entry_id}-{thing_id}-{slug}"
        self._attr_name = "Validate Setup"

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    async def async_press(self) -> None:
        checks: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []

        remote_enabled = bool(
            self._entry.options.get(
                CONF_ENABLE_REMOTE_CONTROL,
                self._entry.data.get(CONF_ENABLE_REMOTE_CONTROL, False),
            )
        )
        if remote_enabled:
            checks.append("Remote control is enabled")
        else:
            errors.append("Remote control is disabled")

        alexa_enabled = bool(self._entry.options.get(CONF_ENABLE_ALEXA_SCENES, True))
        if alexa_enabled:
            checks.append("Alexa routine scenes are enabled")
        else:
            warnings.append("Alexa routine scenes are disabled")

        target_collective = str(
            self._entry.options.get(CONF_ALEXA_TARGET_COLLECTIVE, self._thing_id)
        ).strip() or self._thing_id
        if target_collective in self._hub.collective_ids:
            checks.append(f"Target collective is valid: {target_collective}")
        else:
            errors.append(f"Target collective is not part of this entry: {target_collective}")

        available_modes: list[str] = []
        try:
            config = await self._hub.async_get_collective_config(target_collective)
            available_modes = extract_mode_options(config)
            if available_modes:
                checks.append(f"Found {len(available_modes)} mode options in Hydros config")
            else:
                warnings.append("Could not discover mode options from collective config")
        except Exception as err:  # noqa: BLE001
            errors.append(f"Unable to fetch collective config: {err}")

        def _validate_scene(scene_name_key: str, scene_mode_key: str, label: str) -> None:
            scene_name = str(self._entry.options.get(scene_name_key, "")).strip()
            scene_mode = str(self._entry.options.get(scene_mode_key, "")).strip()
            if not scene_name and not scene_mode:
                warnings.append(f"{label} scene is not configured")
                return
            if not scene_name:
                errors.append(f"{label} scene is missing a scene name")
            if not scene_mode:
                errors.append(f"{label} scene is missing a start mode")
            if scene_name and scene_mode:
                checks.append(f"{label} scene configured: '{scene_name}' -> '{scene_mode}'")
            if available_modes and scene_mode and scene_mode not in available_modes:
                errors.append(
                    f"{label} scene mode '{scene_mode}' is not in discovered modes: {', '.join(available_modes)}"
                )

        _validate_scene(CONF_ALEXA_FEED_SCENE_NAME, CONF_ALEXA_FEED_SCENE_MODE, "Feed")
        _validate_scene(CONF_ALEXA_MAINT_SCENE_NAME, CONF_ALEXA_MAINT_SCENE_MODE, "Maintenance")
        _validate_scene(CONF_ALEXA_CUSTOM_SCENE_NAME, CONF_ALEXA_CUSTOM_SCENE_MODE, "Custom")

        lines = ["Hydros setup validation report", ""]
        if checks:
            lines.append("Checks")
            lines.extend([f"- {item}" for item in checks])
            lines.append("")
        if warnings:
            lines.append("Warnings")
            lines.extend([f"- {item}" for item in warnings])
            lines.append("")
        if errors:
            lines.append("Errors")
            lines.extend([f"- {item}" for item in errors])

        title = "Hydros setup validation"
        if errors:
            title = "Hydros setup validation: issues found"

        persistent_notification.async_create(
            self.hass,
            "\n".join(lines).strip(),
            title=title,
            notification_id=f"hydros_setup_validation_{self._entry.entry_id}_{target_collective}",
        )
