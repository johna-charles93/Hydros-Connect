"""End-to-end setup test for the HYDROS Public API data path."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydros.api import HydrosSession
from custom_components.hydros.const import (
    AUTH_MODE_API,
    CONF_AUTH_MODE,
    CONF_DEVICE_ID,
    CONF_DEVICE_KEY,
    CONF_ENABLE_REMOTE_CONTROL,
    CONF_KEY_PERMISSION,
    CONF_PROVIDER_KEY,
    DOMAIN,
    KEY_PERMISSION_WRITE,
)

_METADATA = [
    {"key": "uuid-return", "name": "Return Pump", "type": "level", "min": 0, "max": 10000},
    {"key": "uuid-heater", "name": "Heater", "type": "bool"},
    {
        "key": "uuid-doser",
        "name": "Alk Doser",
        "type": "bool",
        "commands": {"dose": {"arg": {"min": 1, "max": 5000, "unit": "0.1 mL"}}},
    },
    {"key": "mode", "name": "Mode", "type": "mode", "commands": {"Normal": {}, "Feeding": {}}},
]

_STATE = {
    "mode": "Normal",
    "version": "Quatro-380",
    "Input": {
        "Temperature 1": {"senseValue": 25.9},
        "pH": {"probeValue": 8.05, "probeRawValue": -300},
    },
    "Output": {
        "Return Pump": {"valueState": 7500, "override": False},
        "Heater": {"valueState": 0, "override": False},
        "Alk Doser": {"valueState": 0, "override": False, "reservoir": 1200},
    },
}


def _mock_api_client() -> AsyncMock:
    client = AsyncMock()
    client.async_get_device.return_value = {
        "deviceId": "a0b765227294",
        "friendlyName": "Display Tank",
        "type": "X4",
    }
    client.async_get_override_metadata.return_value = _METADATA
    client.async_start_session.return_value = HydrosSession(
        poll_url="https://api.test/api/v1/device/state?id=s1",
        poll_token="tok",
        poll_interval_seconds=30,
        expires_at=dt_util.utcnow() + timedelta(hours=6),
        started_at=dt_util.utcnow(),
    )
    client.async_poll_state.return_value = _STATE
    client.async_put_overrides.return_value = {"status": "pending", "overrides": {}}
    client.async_send_command.return_value = {"command": "Feeding", "published": True}
    return client


@pytest.fixture
def api_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Display Tank",
        unique_id="api:a0b765227294",
        data={
            CONF_AUTH_MODE: AUTH_MODE_API,
            CONF_PROVIDER_KEY: "prov",
            CONF_DEVICE_KEY: "dev",
            CONF_DEVICE_ID: "a0b765227294",
            CONF_KEY_PERMISSION: KEY_PERMISSION_WRITE,
        },
        options={CONF_ENABLE_REMOTE_CONTROL: True},
    )
    entry.add_to_hass(hass)
    return entry


async def test_api_entry_sets_up_and_builds_entities(
    hass: HomeAssistant, api_entry: MockConfigEntry
) -> None:
    with patch(
        "custom_components.hydros.api_hub.HydrosPublicApiClient",
        return_value=_mock_api_client(),
    ):
        assert await hass.config_entries.async_setup(api_entry.entry_id)
        await hass.async_block_till_done()

    entity_ids = hass.states.async_entity_ids()

    # Input sensors classified from name/fields.
    assert any(
        e.startswith("sensor.") and "temperature_1" in e for e in entity_ids
    ), entity_ids
    assert any(e.startswith("sensor.") and e.endswith("_ph") or "_p_h" in e for e in entity_ids)

    # Mode select + a mode sensor exist (remote control enabled).
    assert any(e.startswith("select.") for e in entity_ids), entity_ids

    # Heater is a bool override -> binary sensor.
    assert any(e.startswith("binary_sensor.") for e in entity_ids), entity_ids

    # Variable pump -> number entity for speed.
    assert any(e.startswith("number.") for e in entity_ids), entity_ids

    # Clean teardown cancels the poll interval.
    assert await hass.config_entries.async_unload(api_entry.entry_id)
    await hass.async_block_till_done()


async def test_api_entry_loads_when_backend_step_fails(
    hass: HomeAssistant, api_entry: MockConfigEntry
) -> None:
    """A 5xx on metadata/session/poll must not block the whole entry."""
    from custom_components.hydros.api import HydrosApiError

    client = _mock_api_client()
    err = HydrosApiError(
        "Internal server error: Invalid thing name specified in request", status=500
    )
    client.async_get_override_metadata.side_effect = err
    client.async_start_session.side_effect = err
    client.async_poll_state.side_effect = err

    with patch(
        "custom_components.hydros.api_hub.HydrosPublicApiClient", return_value=client
    ):
        # GET /device still succeeds, so the entry should load (degraded).
        assert await hass.config_entries.async_setup(api_entry.entry_id)
        await hass.async_block_till_done()

    hub = hass.data[DOMAIN][api_entry.entry_id]["hub"]
    health = hub.get_api_health()
    assert health["status"] == "degraded"
    assert "Invalid thing name" in (health["last_error"] or "")


async def test_api_entry_not_ready_when_get_device_fails(
    hass: HomeAssistant, api_entry: MockConfigEntry
) -> None:
    from homeassistant.config_entries import ConfigEntryState

    from custom_components.hydros.api import HydrosApiError

    client = _mock_api_client()
    client.async_get_device.side_effect = HydrosApiError("gateway down", status=500)

    with patch(
        "custom_components.hydros.api_hub.HydrosPublicApiClient", return_value=client
    ):
        await hass.config_entries.async_setup(api_entry.entry_id)
        await hass.async_block_till_done()

    assert api_entry.state is ConfigEntryState.SETUP_RETRY


async def test_api_hub_change_mode_calls_command(
    hass: HomeAssistant, api_entry: MockConfigEntry
) -> None:
    client = _mock_api_client()
    with patch(
        "custom_components.hydros.api_hub.HydrosPublicApiClient", return_value=client
    ):
        assert await hass.config_entries.async_setup(api_entry.entry_id)
        await hass.async_block_till_done()

        hub = hass.data[DOMAIN][api_entry.entry_id]["hub"]
        await hub.async_change_mode("a0b765227294", "Feeding")

    client.async_send_command.assert_awaited()
    args, kwargs = client.async_send_command.call_args
    assert args[0] == "mode"
    assert args[1] == "Feeding"


async def test_api_hub_pump_speed_scales_to_level(
    hass: HomeAssistant, api_entry: MockConfigEntry
) -> None:
    client = _mock_api_client()
    with patch(
        "custom_components.hydros.api_hub.HydrosPublicApiClient", return_value=client
    ):
        assert await hass.config_entries.async_setup(api_entry.entry_id)
        await hass.async_block_till_done()

        hub = hass.data[DOMAIN][api_entry.entry_id]["hub"]
        await hub.async_set_pump_speed("a0b765227294", "Return Pump", 42.0)

    client.async_put_overrides.assert_awaited()
    payload = client.async_put_overrides.call_args.args[0]
    assert payload == {"uuid-return": 4200}
