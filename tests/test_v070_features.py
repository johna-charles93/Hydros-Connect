"""Tests for v0.7.0: reconfigure, repairs, diagnostics, dosing estimate, entity flags."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
from custom_components.hydros.diagnostics import async_get_config_entry_diagnostics
from custom_components.hydros.dosing_estimate import DoseAccumulator

from test_api_hub_setup import _mock_api_client

D1 = date(2026, 10, 14)
D2 = date(2026, 10, 15)


# ---------------------------------------------------------------- dosing math


def test_accumulator_counts_drops_ignores_refills_and_glitches() -> None:
    acc = DoseAccumulator(day=D1)
    acc.add_reading(1000, D1)  # baseline
    acc.add_reading(995, D1)
    acc.add_reading(990, D1)
    assert acc.today_ml == 10
    acc.add_reading(2000, D1)  # refill -> ignored, new baseline
    acc.add_reading(1997, D1)
    assert acc.today_ml == 13
    acc.add_reading(1500, D1)  # 497 mL in one reading -> glitch, ignored
    assert acc.today_ml == 13
    assert acc.last_reading == 1500


def test_accumulator_rolls_day_and_estimates_days_remaining() -> None:
    acc = DoseAccumulator(day=D1)
    acc.add_reading(1000, D1)
    acc.add_reading(980, D1)
    acc.add_reading(975, D2)  # new day: yesterday's 20 mL archived
    assert acc.history == [{"date": "2026-10-14", "ml": 20.0}]
    assert acc.today_ml == 5
    assert acc.average_daily_ml == 20.0
    assert acc.days_remaining(500) == 25.0
    assert DoseAccumulator(day=D1).days_remaining(500) is None


def test_accumulator_history_is_capped() -> None:
    acc = DoseAccumulator(day=D1)
    for i in range(10):
        acc.today_ml = 1
        acc.roll_day(date(2026, 11, 1 + i))
    assert len(acc.history) == 7


# ---------------------------------------------------------------- fixtures


def _entry(hass: HomeAssistant, permission: str = KEY_PERMISSION_WRITE) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Display Tank",
        unique_id="api:a0b765227294",
        data={
            CONF_AUTH_MODE: AUTH_MODE_API,
            CONF_PROVIDER_KEY: "prov_secret",
            CONF_DEVICE_KEY: "dev_secret",
            CONF_DEVICE_ID: "a0b765227294",
            CONF_KEY_PERMISSION: permission,
        },
        options={CONF_ENABLE_REMOTE_CONTROL: True},
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, client=None):
    client = client or _mock_api_client()
    with patch("custom_components.hydros.api_hub.HydrosPublicApiClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return client


# ---------------------------------------------------------------- reconfigure


def _flow_client(device_id: str = "a0b765227294", writable: bool = True) -> AsyncMock:
    client = AsyncMock()
    client.async_get_device.return_value = {"deviceId": device_id, "friendlyName": "Display Tank"}
    client.async_probe_write_permission.return_value = writable
    return client


async def test_reconfigure_updates_keys_in_place(hass: HomeAssistant) -> None:
    entry = _entry(hass, permission="read")
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    with patch(
        "custom_components.hydros.config_flow.HydrosPublicApiClient",
        return_value=_flow_client(),
    ), patch("custom_components.hydros.api_hub.HydrosPublicApiClient", return_value=_mock_api_client()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PROVIDER_KEY: "prov_new", CONF_DEVICE_KEY: "dev_new"}
        )
        await hass.async_block_till_done()
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DEVICE_KEY] == "dev_new"
    assert entry.data[CONF_PROVIDER_KEY] == "prov_new"
    assert entry.data[CONF_KEY_PERMISSION] == KEY_PERMISSION_WRITE
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure_rejects_other_device(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.hydros.config_flow.HydrosPublicApiClient",
        return_value=_flow_client(device_id="ffffffffffff"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PROVIDER_KEY: "p", CONF_DEVICE_KEY: "d"}
        )
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_DEVICE_KEY] == "dev_secret"


# ---------------------------------------------------------------- repairs


async def test_read_only_key_with_remote_control_raises_issue(hass: HomeAssistant) -> None:
    entry = _entry(hass, permission="read")
    client = _mock_api_client()
    client.async_probe_write_permission.return_value = False
    await _setup(hass, entry, client)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"read_only_key_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "read_only_key"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_writable_key_has_no_issue(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    await _setup(hass, entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"read_only_key_{entry.entry_id}") is None
    await hass.config_entries.async_unload(entry.entry_id)


# ---------------------------------------------------------------- diagnostics + entities


async def test_diagnostics_redacts_keys(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    await _setup(hass, entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    assert "prov_secret" not in text and "dev_secret" not in text
    assert diag["entry"]["data"][CONF_DEVICE_KEY] == "**REDACTED**"
    assert diag["hub"]["write_capable"] is True
    assert diag["entities"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_entity_flags_and_doser_extras(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    await _setup(hass, entry)
    reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(reg, entry.entry_id)

    debug = [e for e in entries if e.entity_id.startswith("button.") and "debug" in e.entity_id]
    assert debug and all(e.entity_category == er.EntityCategory.DIAGNOSTIC for e in debug)

    api_status = [e for e in entries if "api_status" in e.entity_id]
    assert api_status and api_status[0].entity_category == er.EntityCategory.DIAGNOSTIC

    estimate = [e for e in entries if "dosed_today_estimated" in e.entity_id]
    assert len(estimate) == 1, [e.entity_id for e in entries]
    state = hass.states.get(estimate[0].entity_id)
    assert state is not None and state.attributes.get("estimated") is True

    reservoir = [e for e in entries if "reservoir" in e.entity_id]
    assert reservoir
    rstate = hass.states.get(reservoir[0].entity_id)
    assert rstate.attributes.get("thing_id") == "a0b765227294"
    assert rstate.attributes.get("output_key") == "Alk Doser"
    await hass.config_entries.async_unload(entry.entry_id)
