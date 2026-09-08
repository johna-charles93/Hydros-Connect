"""Tests for Hydros Alexa routine scene entities (issue #3)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydros.const import (
    AUTH_MODE_API,
    CONF_ALEXA_EASY_SETUP,
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
from custom_components.hydros.scene import HydrosModeRoutineScene, _PresetConfig
from tests.test_api_hub_setup import _mock_api_client


def _preset(name: str, key: str = "feed") -> _PresetConfig:
    return _PresetConfig(
        key=key,
        display_name=name,
        start_mode="Feeding",
        return_enabled=False,
        return_delay_minutes=15,
        return_mode="",
    )


def test_scene_unique_id_stable_across_rename() -> None:
    hub = SimpleNamespace(entry_id="entry123")

    before = HydrosModeRoutineScene(
        hub=hub, thing_id="Reef Tank", preset=_preset("Feed Mode"),
        return_manager=None, device_info=None,
    )
    after = HydrosModeRoutineScene(
        hub=hub, thing_id="Reef Tank", preset=_preset("Feeding Time"),
        return_manager=None, device_info=None,
    )

    # Renaming the scene must NOT change its identity...
    assert before.unique_id == after.unique_id == "entry123-reef_tank-feed-scene"
    # ...but the suggested entity_id still tracks the current name on first create.
    assert before.entity_id == "scene.feed_mode"
    assert after.entity_id == "scene.feeding_time"


@pytest.fixture
def scene_entry(hass: HomeAssistant) -> MockConfigEntry:
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
        options={
            CONF_ENABLE_REMOTE_CONTROL: True,
            CONF_ENABLE_ALEXA_SCENES: True,
            CONF_ALEXA_EASY_SETUP: True,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_prunes_orphaned_scene_entities(
    hass: HomeAssistant, scene_entry: MockConfigEntry
) -> None:
    registry = er.async_get(hass)
    # Simulate an orphan left by an older version's name-based unique_id.
    stale = registry.async_get_or_create(
        "scene",
        DOMAIN,
        "old-name-based-unique-id-scene",
        config_entry=scene_entry,
        suggested_object_id="feed_mode",
    )
    assert registry.async_get(stale.entity_id) is not None

    with patch(
        "custom_components.hydros.api_hub.HydrosPublicApiClient",
        return_value=_mock_api_client(),
    ):
        assert await hass.config_entries.async_setup(scene_entry.entry_id)
        await hass.async_block_till_done()

    live = [
        e
        for e in registry.entities.values()
        if e.config_entry_id == scene_entry.entry_id
        and e.domain == "scene"
        and e.platform == DOMAIN
    ]
    assert live, "expected at least one Hydros scene entity"
    # The old name-based unique_id is gone entirely...
    assert all(e.unique_id != "old-name-based-unique-id-scene" for e in live)
    # ...replaced by stable slot-based ids.
    assert all(e.unique_id.endswith("-scene") for e in live)
    assert {e.unique_id.split("-")[-2] for e in live} == {"feed", "maintenance"}
    # The user's existing entity_id is preserved and now backed by a live scene.
    reclaimed = registry.async_get(stale.entity_id)
    assert reclaimed is not None
    assert reclaimed.unique_id != "old-name-based-unique-id-scene"
    assert reclaimed.unique_id.endswith("-feed-scene")
