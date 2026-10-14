"""Diagnostics download (Settings → Devices & services → Hydros → ⋮ → Download diagnostics)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_DEVICE_KEY, CONF_PROVIDER_KEY, DOMAIN

TO_REDACT = {
    CONF_PROVIDER_KEY,
    CONF_DEVICE_KEY,
    "password",
    "username",
    "token",
    "poll_token",
    "pollToken",
    "pollUrl",
    "poll_url",
    "_hydros_key",
    "key",
    "email",
}


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    hub = entry_data.get("hub") if isinstance(entry_data, dict) else None

    hub_info: dict[str, Any] = {}
    if hub is not None:
        health = {}
        getter = getattr(hub, "get_api_health", None)
        if callable(getter):
            health = {k: _iso(v) for k, v in (getter() or {}).items()}
        hub_info = {
            "type": type(hub).__name__,
            "collective_ids": list(getattr(hub, "collective_ids", []) or []),
            "write_capable": getattr(hub, "_write_capable", None),
            "api_health": health,
            "device_meta": getattr(hub, "_device_meta", None),
            "override_metadata": {
                name: {
                    "type": getattr(om, "type", None),
                    "commands": sorted(getattr(om, "commands", {}) or {}),
                    "dose_arg": getattr(om, "dose_arg", None),
                }
                for name, om in (getattr(hub, "_override_meta", {}) or {}).items()
            },
            "mode_commands": list(getattr(hub, "_mode_commands", []) or []),
            "last_state": getattr(hub, "_status_payload", None),
            "device_offline": getattr(hub, "_device_offline", None),
        }

    registry = er.async_get(hass)
    entities = [
        {
            "entity_id": e.entity_id,
            "disabled_by": e.disabled_by,
            "entity_category": e.entity_category,
            "state": (s.state if (s := hass.states.get(e.entity_id)) else None),
        }
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    ]

    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "version": entry.version,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "hub": hub_info,
            "entities": entities,
        },
        TO_REDACT,
    )
