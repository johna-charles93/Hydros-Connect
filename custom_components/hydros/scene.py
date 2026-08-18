from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    CONF_ALEXA_CUSTOM_RETURN_DELAY_MINUTES,
    CONF_ALEXA_CUSTOM_RETURN_ENABLED,
    CONF_ALEXA_CUSTOM_RETURN_MODE,
    CONF_ALEXA_CUSTOM_SCENE_MODE,
    CONF_ALEXA_CUSTOM_SCENE_NAME,
    CONF_ALEXA_FEED_RETURN_DELAY_MINUTES,
    CONF_ALEXA_FEED_RETURN_ENABLED,
    CONF_ALEXA_FEED_RETURN_MODE,
    CONF_ALEXA_FEED_SCENE_MODE,
    CONF_ALEXA_FEED_SCENE_NAME,
    CONF_ALEXA_MAINT_RETURN_DELAY_MINUTES,
    CONF_ALEXA_MAINT_RETURN_ENABLED,
    CONF_ALEXA_MAINT_RETURN_MODE,
    CONF_ALEXA_MAINT_SCENE_MODE,
    CONF_ALEXA_MAINT_SCENE_NAME,
    CONF_ALEXA_TARGET_COLLECTIVE,
    CONF_ENABLE_ALEXA_SCENES,
    CONF_ENABLE_REMOTE_CONTROL,
    DEFAULT_ALEXA_CUSTOM_RETURN_DELAY_MINUTES,
    DEFAULT_ALEXA_CUSTOM_RETURN_ENABLED,
    DEFAULT_ALEXA_CUSTOM_RETURN_MODE,
    DEFAULT_ALEXA_CUSTOM_SCENE_MODE,
    DEFAULT_ALEXA_CUSTOM_SCENE_NAME,
    DEFAULT_ALEXA_FEED_RETURN_DELAY_MINUTES,
    DEFAULT_ALEXA_FEED_RETURN_ENABLED,
    DEFAULT_ALEXA_FEED_RETURN_MODE,
    DEFAULT_ALEXA_FEED_SCENE_MODE,
    DEFAULT_ALEXA_FEED_SCENE_NAME,
    DEFAULT_ALEXA_MAINT_RETURN_DELAY_MINUTES,
    DEFAULT_ALEXA_MAINT_RETURN_ENABLED,
    DEFAULT_ALEXA_MAINT_RETURN_MODE,
    DEFAULT_ALEXA_MAINT_SCENE_MODE,
    DEFAULT_ALEXA_MAINT_SCENE_NAME,
    DEFAULT_ENABLE_ALEXA_SCENES,
    DOMAIN,
)
from .hydros_hub import HydrosHub

_LOGGER = logging.getLogger(__name__)


@dataclass
class _PresetConfig:
    key: str
    display_name: str
    start_mode: str
    return_enabled: bool
    return_delay_minutes: int
    return_mode: str


def _is_remote_control_enabled(entry: ConfigEntry) -> bool:
    return bool(
        entry.options.get(
            CONF_ENABLE_REMOTE_CONTROL,
            entry.data.get(CONF_ENABLE_REMOTE_CONTROL, False),
        )
    )


def _is_alexa_scenes_enabled(entry: ConfigEntry) -> bool:
    return bool(
        entry.options.get(
            CONF_ENABLE_ALEXA_SCENES,
            DEFAULT_ENABLE_ALEXA_SCENES,
        )
    )


def _clean_str(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _coerce_positive_int(value: object, default: int) -> int:
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, candidate)


def _build_presets(entry: ConfigEntry) -> list[_PresetConfig]:
    options = entry.options

    presets = [
        _PresetConfig(
            key="feed",
            display_name=_clean_str(options.get(CONF_ALEXA_FEED_SCENE_NAME, DEFAULT_ALEXA_FEED_SCENE_NAME)),
            start_mode=_clean_str(options.get(CONF_ALEXA_FEED_SCENE_MODE, DEFAULT_ALEXA_FEED_SCENE_MODE)),
            return_enabled=bool(
                options.get(CONF_ALEXA_FEED_RETURN_ENABLED, DEFAULT_ALEXA_FEED_RETURN_ENABLED)
            ),
            return_delay_minutes=_coerce_positive_int(
                options.get(
                    CONF_ALEXA_FEED_RETURN_DELAY_MINUTES,
                    DEFAULT_ALEXA_FEED_RETURN_DELAY_MINUTES,
                ),
                DEFAULT_ALEXA_FEED_RETURN_DELAY_MINUTES,
            ),
            return_mode=_clean_str(options.get(CONF_ALEXA_FEED_RETURN_MODE, DEFAULT_ALEXA_FEED_RETURN_MODE)),
        ),
        _PresetConfig(
            key="maintenance",
            display_name=_clean_str(options.get(CONF_ALEXA_MAINT_SCENE_NAME, DEFAULT_ALEXA_MAINT_SCENE_NAME)),
            start_mode=_clean_str(options.get(CONF_ALEXA_MAINT_SCENE_MODE, DEFAULT_ALEXA_MAINT_SCENE_MODE)),
            return_enabled=bool(
                options.get(CONF_ALEXA_MAINT_RETURN_ENABLED, DEFAULT_ALEXA_MAINT_RETURN_ENABLED)
            ),
            return_delay_minutes=_coerce_positive_int(
                options.get(
                    CONF_ALEXA_MAINT_RETURN_DELAY_MINUTES,
                    DEFAULT_ALEXA_MAINT_RETURN_DELAY_MINUTES,
                ),
                DEFAULT_ALEXA_MAINT_RETURN_DELAY_MINUTES,
            ),
            return_mode=_clean_str(options.get(CONF_ALEXA_MAINT_RETURN_MODE, DEFAULT_ALEXA_MAINT_RETURN_MODE)),
        ),
        _PresetConfig(
            key="custom",
            display_name=_clean_str(options.get(CONF_ALEXA_CUSTOM_SCENE_NAME, DEFAULT_ALEXA_CUSTOM_SCENE_NAME)),
            start_mode=_clean_str(options.get(CONF_ALEXA_CUSTOM_SCENE_MODE, DEFAULT_ALEXA_CUSTOM_SCENE_MODE)),
            return_enabled=bool(
                options.get(CONF_ALEXA_CUSTOM_RETURN_ENABLED, DEFAULT_ALEXA_CUSTOM_RETURN_ENABLED)
            ),
            return_delay_minutes=_coerce_positive_int(
                options.get(
                    CONF_ALEXA_CUSTOM_RETURN_DELAY_MINUTES,
                    DEFAULT_ALEXA_CUSTOM_RETURN_DELAY_MINUTES,
                ),
                DEFAULT_ALEXA_CUSTOM_RETURN_DELAY_MINUTES,
            ),
            return_mode=_clean_str(options.get(CONF_ALEXA_CUSTOM_RETURN_MODE, DEFAULT_ALEXA_CUSTOM_RETURN_MODE)),
        ),
    ]

    enabled: list[_PresetConfig] = []
    for preset in presets:
        if not preset.display_name or not preset.start_mode:
            continue
        if preset.return_enabled and not preset.return_mode:
            continue
        enabled.append(preset)

    return enabled


def _resolve_target_collective(entry: ConfigEntry, hub: HydrosHub) -> str | None:
    configured = _clean_str(entry.options.get(CONF_ALEXA_TARGET_COLLECTIVE, ""))
    if configured and configured in hub.collective_ids:
        return configured
    return hub.collective_ids[0] if hub.collective_ids else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not _is_remote_control_enabled(entry):
        return
    if not _is_alexa_scenes_enabled(entry):
        return

    entry_data = hass.data[DOMAIN][entry.entry_id]
    if isinstance(entry_data, HydrosHub):
        entry_data = {"hub": entry_data}
        hass.data[DOMAIN][entry.entry_id] = entry_data

    hub: HydrosHub = entry_data["hub"]
    thing_id = _resolve_target_collective(entry, hub)
    if not thing_id:
        return

    metadata = hub.get_collective_metadata(thing_id) or {}
    device_name = metadata.get("friendlyName") or metadata.get("thingName") or thing_id
    manufacturer = metadata.get("manufacturer") or "Hydros"
    model = metadata.get("thingType") or metadata.get("type")

    presets = _build_presets(entry)
    entities: list[HydrosModeRoutineScene] = []
    for preset in presets:
        entities.append(
            HydrosModeRoutineScene(
                hub=hub,
                thing_id=thing_id,
                preset=preset,
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


class HydrosModeRoutineScene(Scene):
    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        hub: HydrosHub,
        thing_id: str,
        preset: _PresetConfig,
        device_info: DeviceInfo,
    ) -> None:
        self._hub = hub
        self._thing_id = thing_id
        self._preset = preset
        self._device_info = device_info

        slug = slugify(f"{thing_id}-{preset.key}-{preset.display_name}")
        self._attr_unique_id = f"{hub.entry_id}-{slug}-scene"
        self._attr_name = preset.display_name

    @property
    def device_info(self) -> DeviceInfo:
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attrs: dict[str, object] = {
            "thing_id": self._thing_id,
            "start_mode": self._preset.start_mode,
            "return_enabled": self._preset.return_enabled,
        }
        if self._preset.return_enabled:
            attrs["return_mode"] = self._preset.return_mode
            attrs["return_delay_minutes"] = self._preset.return_delay_minutes
        return attrs

    async def async_activate(self, **kwargs: object) -> None:
        del kwargs
        await self._hub.async_change_mode(self._thing_id, self._preset.start_mode)

        if not self._preset.return_enabled:
            return

        delay_seconds = int(self._preset.return_delay_minutes) * 60
        return_mode = self._preset.return_mode

        async def _delayed_return() -> None:
            await asyncio.sleep(delay_seconds)
            try:
                await self._hub.async_change_mode(self._thing_id, return_mode)
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Hydros routine scene failed to return mode for %s",
                    self.entity_id,
                    exc_info=True,
                )

        self.hass.async_create_task(_delayed_return())
