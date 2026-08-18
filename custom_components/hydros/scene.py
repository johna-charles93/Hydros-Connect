from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from homeassistant.components.persistent_notification import async_create

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
_STORE_VERSION = 1
_STORE_KEY_PREFIX = f"{DOMAIN}_scene_returns"


@dataclass
class _PresetConfig:
    key: str
    display_name: str
    start_mode: str
    return_enabled: bool
    return_delay_minutes: int
    return_mode: str


@dataclass
class _ScheduledReturn:
    key: str
    thing_id: str
    mode: str
    run_at: str


class HydrosSceneReturnManager:
    def __init__(self, hass: HomeAssistant, *, entry_id: str, hub: HydrosHub) -> None:
        self._hass = hass
        self._hub = hub
        self._entry_id = entry_id
        self._store = Store[list[dict[str, Any]]](
            hass,
            _STORE_VERSION,
            f"{_STORE_KEY_PREFIX}_{entry_id}",
        )
        self._unsubs: dict[str, Any] = {}
        self._scheduled: dict[str, _ScheduledReturn] = {}

    async def async_initialize(self) -> None:
        raw = await self._store.async_load() or []
        now = dt_util.utcnow()
        changed = False

        for item in raw:
            key = str(item.get("key", "")).strip()
            thing_id = str(item.get("thing_id", "")).strip()
            mode = str(item.get("mode", "")).strip()
            run_at_raw = str(item.get("run_at", "")).strip()
            if not key or not thing_id or not mode or not run_at_raw:
                changed = True
                continue

            run_at = dt_util.parse_datetime(run_at_raw)
            if run_at is None:
                changed = True
                continue
            if run_at.tzinfo is None:
                run_at = dt_util.as_utc(run_at)
            if run_at <= now:
                changed = True
                continue

            self._scheduled[key] = _ScheduledReturn(
                key=key,
                thing_id=thing_id,
                mode=mode,
                run_at=run_at.isoformat(),
            )
            self._schedule_callback(key, thing_id, mode, run_at)

        if changed:
            await self._async_persist()

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs.values():
            unsub()
        self._unsubs.clear()

    async def async_schedule_return(
        self,
        *,
        key: str,
        thing_id: str,
        mode: str,
        delay_minutes: int,
    ) -> None:
        if key in self._unsubs:
            self._unsubs[key]()
            self._unsubs.pop(key, None)

        run_at = dt_util.utcnow() + timedelta(minutes=max(1, int(delay_minutes)))
        self._scheduled[key] = _ScheduledReturn(
            key=key,
            thing_id=thing_id,
            mode=mode,
            run_at=run_at.isoformat(),
        )
        self._schedule_callback(key, thing_id, mode, run_at)
        await self._async_persist()

    def _schedule_callback(self, key: str, thing_id: str, mode: str, run_at: Any) -> None:
        @callback
        def _handle_due(_: Any) -> None:
            self._hass.async_create_task(self._async_execute_return(key, thing_id, mode))

        self._unsubs[key] = async_track_point_in_utc_time(self._hass, _handle_due, run_at)

    async def _async_execute_return(self, key: str, thing_id: str, mode: str) -> None:
        self._unsubs.pop(key, None)
        self._scheduled.pop(key, None)
        await self._async_persist()

        try:
            await self._hub.async_change_mode(thing_id, mode)
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Hydros routine scene failed to return mode (key=%s)",
                key,
                exc_info=True,
            )

    async def _async_persist(self) -> None:
        payload = [
            {
                "key": record.key,
                "thing_id": record.thing_id,
                "mode": record.mode,
                "run_at": record.run_at,
            }
            for record in self._scheduled.values()
        ]
        await self._store.async_save(payload)


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
        _LOGGER.debug("Skipping scene setup: remote control disabled for entry %s", entry.entry_id)
        return
    if not _is_alexa_scenes_enabled(entry):
        _LOGGER.debug("Skipping scene setup: Alexa scenes disabled for entry %s", entry.entry_id)
        return

    _LOGGER.debug("Setting up Hydros Alexa scenes for entry %s", entry.entry_id)

    entry_data = hass.data[DOMAIN][entry.entry_id]
    if isinstance(entry_data, HydrosHub):
        entry_data = {"hub": entry_data}
        hass.data[DOMAIN][entry.entry_id] = entry_data

    hub: HydrosHub = entry_data["hub"]
    manager = entry_data.get("scene_return_manager")
    if not isinstance(manager, HydrosSceneReturnManager):
        manager = HydrosSceneReturnManager(hass, entry_id=entry.entry_id, hub=hub)
        entry_data["scene_return_manager"] = manager
        await manager.async_initialize()

    thing_id = _resolve_target_collective(entry, hub)
    if not thing_id:
        _LOGGER.warning("No target collective resolved for scene setup in entry %s", entry.entry_id)
        return

    metadata = hub.get_collective_metadata(thing_id) or {}
    device_name = metadata.get("friendlyName") or metadata.get("thingName") or thing_id
    manufacturer = metadata.get("manufacturer") or "Hydros"
    model = metadata.get("thingType") or metadata.get("type")

    presets = _build_presets(entry)
    _LOGGER.debug("Built %d scene presets for thing_id=%s", len(presets), thing_id)
    
    entities: list[HydrosModeRoutineScene] = []
    for preset in presets:
        entities.append(
            HydrosModeRoutineScene(
                hub=hub,
                thing_id=thing_id,
                preset=preset,
                return_manager=manager,
                device_info=DeviceInfo(
                    identifiers={(DOMAIN, thing_id)},
                    name=device_name,
                    manufacturer=manufacturer,
                    model=model,
                ),
            )
        )

    if entities:
        _LOGGER.info("Adding %d Hydros Alexa scenes", len(entities))
        async_add_entities(entities)
        
        # Auto-expose scenes to Alexa via persistent notification
        await _async_notify_alexa_exposure(hass, entry, entities)
    else:
        _LOGGER.warning("No valid scene presets found for entry %s", entry.entry_id)


class HydrosModeRoutineScene(Scene):
    _attr_has_entity_name = False
    _attr_icon = "mdi:play-circle"

    def __init__(
        self,
        *,
        hub: HydrosHub,
        thing_id: str,
        preset: _PresetConfig,
        return_manager: HydrosSceneReturnManager,
        device_info: DeviceInfo,
    ) -> None:
        self._hub = hub
        self._thing_id = thing_id
        self._preset = preset
        self._return_manager = return_manager
        self._device_info = device_info
        self._attr_available = True

        slug = slugify(f"{thing_id}-{preset.key}-{preset.display_name}")
        self._attr_unique_id = f"{hub.entry_id}-{slug}-scene"
        self._attr_name = preset.display_name
        
        _LOGGER.debug(
            "Created scene: %s (unique_id=%s, mode=%s)",
            preset.display_name,
            self._attr_unique_id,
            preset.start_mode,
        )

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
        _LOGGER.info(
            "Activating scene '%s' -> mode '%s' (thing_id=%s)",
            self._attr_name,
            self._preset.start_mode,
            self._thing_id,
        )
        
        try:
            await self._hub.async_change_mode(self._thing_id, self._preset.start_mode)
            _LOGGER.debug(
                "Scene '%s' activated successfully, mode changed to '%s'",
                self._attr_name,
                self._preset.start_mode,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Failed to activate scene '%s': %s",
                self._attr_name,
                err,
                exc_info=True,
            )
            raise

        if not self._preset.return_enabled:
            return

        try:
            await self._return_manager.async_schedule_return(
                key=self._attr_unique_id,
                thing_id=self._thing_id,
                mode=self._preset.return_mode,
                delay_minutes=self._preset.return_delay_minutes,
            )
            _LOGGER.debug(
                "Scene '%s' scheduled auto-return to '%s' in %d minutes",
                self._attr_name,
                self._preset.return_mode,
                self._preset.return_delay_minutes,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to schedule return for scene '%s': %s",
                self._attr_name,
                err,
                exc_info=True,
            )


async def _async_notify_alexa_exposure(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entities: list[HydrosModeRoutineScene],
) -> None:
    """Create persistent notification guiding users to expose scenes to Alexa."""
    if not entities:
        return

    # Check if we've already notified for this entry
    notification_key = f"hydros_alexa_setup_{entry.entry_id}"
    stored_notified = hass.data.get("hydros_alexa_notified", {})
    if stored_notified.get(entry.entry_id):
        return

    scene_list = "\n".join([f"• {entity.name}" for entity in entities])

    notification_msg = f"""
**Hydros Scenes Ready for Alexa!**

Your Alexa mode scenes are set up and ready. Here's how to use them:

**Scenes created:**
{scene_list}

**Next step:**
1. Open **Settings → Devices & Services → Alexa** in Home Assistant
2. Click the three dots (⋮) → **Manage Entities**
3. Search for "hydros" or your scene names above
4. Toggle them ON to expose to Alexa

**Then ask Alexa:**
- "Alexa, activate Feed Mode"
- "Alexa, turn on Maintenance Mode"
- Or set them up in Alexa routines for custom voice phrases

Need help? Check the [Hydros README](https://github.com/johna-charles93/Hydros-Connect/blob/main/custom_components/hydros/README.md#alexa-setup)
"""

    if not stored_notified:
        hass.data["hydros_alexa_notified"] = {}

    async_create(
        hass,
        notification_msg,
        title="Hydros Alexa Setup",
        notification_id=notification_key,
    )

    hass.data["hydros_alexa_notified"][entry.entry_id] = True
