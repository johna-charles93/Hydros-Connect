"""Shared pytest config for the Hydros integration test-suite."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the `hydros` custom component during tests."""
    yield
