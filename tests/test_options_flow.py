"""Options (Configure) flow tests — issues #7 / #8."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import voluptuous_serialize
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydros.const import (
    AUTH_MODE_API,
    CONF_ACCEPT_REMOTE_CONTROL_DISCLAIMER,
    CONF_ALEXA_CUSTOM_SCENE_MODE,
    CONF_ALEXA_CUSTOM_SCENE_NAME,
    CONF_ALEXA_EASY_SETUP,
    CONF_ALEXA_FEED_SCENE_MODE,
    CONF_ALEXA_FEED_SCENE_NAME,
    CONF_AUTH_MODE,
    CONF_DEVICE_ID,
    CONF_DEVICE_KEY,
    CONF_ENABLE_ALEXA_SCENES,
    CONF_ENABLE_REMOTE_CONTROL,
    CONF_KEY_PERMISSION,
    CONF_PROVIDER_KEY,
    DOMAIN,
    KEY_PERMISSION_WRITE,
)

from test_api_hub_setup import _mock_api_client


@pytest.fixture
async def loaded_entry(hass: HomeAssistant) -> MockConfigEntry:
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
        options={},  # fresh entry: remote control off, nothing configured
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.hydros.api_hub.HydrosPublicApiClient",
        return_value=_mock_api_client(),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


def _required_keys(schema) -> list[str]:
    """Keys the HA frontend would refuse to submit when blank."""
    out = []
    for field in voluptuous_serialize.convert(schema, custom_serializer=cv.custom_serializer):
        if field.get("type") == "expandable":
            out += [
                f"{field['name']}.{f['name']}"
                for f in field["schema"]
                if f.get("required") and "default" not in f
            ]
        elif field.get("required") and "default" not in field:
            out.append(field["name"])
    return out


async def test_options_form_serializes_and_has_no_blank_required_fields(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # Must convert for the frontend (v0.6.6 regression) and must not contain
    # required fields without a value (#7: "Not all required fields are filled in").
    schema = result["data_schema"]
    for field in voluptuous_serialize.convert(schema, custom_serializer=cv.custom_serializer):
        if field.get("type") == "expandable":
            for sub in field["schema"]:
                assert not sub.get("required"), sub
    assert _required_keys(schema) == []


async def test_enable_remote_control_with_blank_optional_fields(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Submit like the frontend does: blank optional fields are simply omitted."""
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ENABLE_REMOTE_CONTROL: True,
            CONF_ENABLE_ALEXA_SCENES: False,
            CONF_ALEXA_EASY_SETUP: False,
            "feed_scene": {},
            "maintenance_scene": {},
            "custom_scene": {},
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "disclaimer"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ACCEPT_REMOTE_CONTROL_DISCLAIMER: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_ENABLE_REMOTE_CONTROL] is True
    assert loaded_entry.options[CONF_ALEXA_CUSTOM_SCENE_NAME] == ""
    assert loaded_entry.options[CONF_ALEXA_CUSTOM_SCENE_MODE] == ""


async def test_section_values_are_saved(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ENABLE_REMOTE_CONTROL: False,
            CONF_ENABLE_ALEXA_SCENES: True,
            CONF_ALEXA_EASY_SETUP: False,
            "feed_scene": {
                CONF_ALEXA_FEED_SCENE_NAME: "Reef Feed",
                CONF_ALEXA_FEED_SCENE_MODE: "Feeding",
            },
            "maintenance_scene": {},
            "custom_scene": {},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert loaded_entry.options[CONF_ALEXA_FEED_SCENE_NAME] == "Reef Feed"
    assert loaded_entry.options[CONF_ALEXA_FEED_SCENE_MODE] == "Feeding"
    assert loaded_entry.options[CONF_ENABLE_REMOTE_CONTROL] is False


async def test_flat_input_still_accepted(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Older clients / scripts submitting flat (non-sectioned) options still work."""
    flow = hass.config_entries.options._progress  # noqa: SLF001
    result = await hass.config_entries.options.async_init(loaded_entry.entry_id)
    handler = flow[result["flow_id"]]
    result = await handler.async_step_init(
        {
            CONF_ENABLE_REMOTE_CONTROL: False,
            CONF_ENABLE_ALEXA_SCENES: True,
            CONF_ALEXA_EASY_SETUP: False,
            CONF_ALEXA_FEED_SCENE_NAME: "Flat Feed",
        }
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ALEXA_FEED_SCENE_NAME] == "Flat Feed"
