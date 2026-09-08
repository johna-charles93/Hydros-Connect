"""Config-flow tests for the official HYDROS Public API auth path."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.hydros.const import (
    AUTH_MODE_API,
    CONF_AUTH_MODE,
    CONF_DEVICE_ID,
    CONF_DEVICE_KEY,
    CONF_KEY_PERMISSION,
    CONF_PROVIDER_KEY,
    DOMAIN,
    KEY_PERMISSION_READ,
    KEY_PERMISSION_WRITE,
)


def _mock_client(*, device=None, writable=True):
    client = AsyncMock()
    client.async_get_device.return_value = device or {
        "deviceId": "a0b765227294",
        "friendlyName": "Display Tank",
        "type": "X4",
    }
    client.async_probe_write_permission.return_value = writable
    return client


async def test_menu_then_api_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert set(result["menu_options"]) == {"api", "legacy"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "api"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "api"

    with patch(
        "custom_components.hydros.config_flow.HydrosPublicApiClient",
        return_value=_mock_client(writable=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PROVIDER_KEY: "prov_abc", CONF_DEVICE_KEY: "dev_xyz"},
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Display Tank"
    assert result["data"] == {
        CONF_AUTH_MODE: AUTH_MODE_API,
        CONF_PROVIDER_KEY: "prov_abc",
        CONF_DEVICE_KEY: "dev_xyz",
        CONF_DEVICE_ID: "a0b765227294",
        CONF_KEY_PERMISSION: KEY_PERMISSION_WRITE,
    }
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == "api:a0b765227294"


async def test_menu_legacy_still_shows_credentials_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "legacy"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "legacy"


async def test_api_read_only_key_is_recorded(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "api"}
    )
    with patch(
        "custom_components.hydros.config_flow.HydrosPublicApiClient",
        return_value=_mock_client(writable=False),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PROVIDER_KEY: "prov_abc", CONF_DEVICE_KEY: "dev_ro"},
        )
    assert result["data"][CONF_KEY_PERMISSION] == KEY_PERMISSION_READ


async def test_api_invalid_auth_shows_error(hass: HomeAssistant) -> None:
    from custom_components.hydros.api import HydrosApiAuthError

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "api"}
    )

    bad = AsyncMock()
    bad.async_get_device.side_effect = HydrosApiAuthError("bad key")
    with patch(
        "custom_components.hydros.config_flow.HydrosPublicApiClient", return_value=bad
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PROVIDER_KEY: "x", CONF_DEVICE_KEY: "y"},
        )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_api_server_error_maps_to_server_error(hass: HomeAssistant) -> None:
    from custom_components.hydros.api import HydrosApiError

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "api"}
    )

    boom = AsyncMock()
    boom.async_get_device.side_effect = HydrosApiError("gateway blew up", status=500)
    with patch(
        "custom_components.hydros.config_flow.HydrosPublicApiClient", return_value=boom
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PROVIDER_KEY: "x", CONF_DEVICE_KEY: "y"},
        )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "server_error"}
    assert "gateway blew up" in result["description_placeholders"]["error_detail"]


async def test_api_duplicate_device_aborts(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(
        domain=DOMAIN,
        unique_id="api:a0b765227294",
        data={CONF_AUTH_MODE: AUTH_MODE_API, CONF_DEVICE_ID: "a0b765227294"},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "api"}
    )
    with patch(
        "custom_components.hydros.config_flow.HydrosPublicApiClient",
        return_value=_mock_client(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PROVIDER_KEY: "prov_abc", CONF_DEVICE_KEY: "dev_xyz"},
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
