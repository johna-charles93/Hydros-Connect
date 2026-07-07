from __future__ import annotations

DOMAIN = "hydros"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_COLLECTIVES = "collectives"
CONF_ENABLE_REMOTE_CONTROL = "enable_remote_control"
CONF_ACCEPT_REMOTE_CONTROL_DISCLAIMER = "accept_remote_control_disclaimer"
DEFAULT_REGION = "us-west-2"
DEFAULT_WATCHDOG_INACTIVITY = 5
DEFAULT_COMMAND_CONFIRM_TIMEOUT = 15
DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS = 1.0
DEFAULT_MODE_COMMAND_COOLDOWN_SECONDS = 2.0
DEFAULT_MAX_MANUAL_DOSE_SECONDS = 1800

PLATFORMS: list[str] = ["sensor", "binary_sensor", "button", "select", "switch", "number"]

SIGNAL_COLLECTIVE_UPDATED = "hydros_collective_updated_{entry}_{thing}"
SIGNAL_CONFIG_UPDATED = "hydros_config_updated_{entry}_{thing}"

SERVICE_SET_OUTPUT_STATE = "set_output_state"
SERVICE_SET_PUMP_SPEED = "set_pump_speed"
SERVICE_CHANGE_MODE = "change_mode"
SERVICE_MANUAL_DOSE = "manual_dose"
