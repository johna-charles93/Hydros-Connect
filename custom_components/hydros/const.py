from __future__ import annotations

DOMAIN = "hydros"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_COLLECTIVES = "collectives"

# ---------------------------------------------------------------------------
# Authentication mode
# ---------------------------------------------------------------------------
# "legacy" — the original reverse-engineered path: HYDROS account email +
#            password, AWS Cognito auth, AWS IoT MQTT for live data, signed-S3
#            config download. Kept working for existing installs.
# "api"    — the official CoralVue HYDROS Public API (https://api.coralvuehydros.com):
#            per-user provider key + device key, REST polling only.
CONF_AUTH_MODE = "auth_mode"
AUTH_MODE_LEGACY = "legacy"
AUTH_MODE_API = "api"

# Official Public API credentials / identifiers.
CONF_PROVIDER_KEY = "provider_key"
CONF_DEVICE_KEY = "device_key"
CONF_DEVICE_ID = "device_id"
CONF_KEY_PERMISSION = "key_permission"  # "read" or "write"

KEY_PERMISSION_READ = "read"
KEY_PERMISSION_WRITE = "write"

# Public API tuning.
HYDROS_API_BASE_URL = "https://api.coralvuehydros.com"
# Server advertises a 30s poll floor; GET /device/state is capped at 10/min.
DEFAULT_API_POLL_INTERVAL = 30
# Session poll tokens live 6h; renew with margin to spare.
DEFAULT_API_SESSION_RENEW_MARGIN = 1800  # 30 minutes
# POST /device/state/session is capped at 5/hour/device. When a session start
# fails, wait at least this long before trying again, doubling up to the max on
# repeated rate-limit responses.
DEFAULT_API_SESSION_RETRY_BASE = 900  # 15 minutes -> <= 4 attempts/hour
DEFAULT_API_SESSION_RETRY_MAX = 3600  # 1 hour
# Override metadata only changes on device reconfiguration; cache aggressively.
DEFAULT_API_METADATA_TTL = 900  # 15 minutes
# After a metadata fetch fails, wait this long before retrying it.
DEFAULT_API_METADATA_RETRY = 300  # 5 minutes
# HTTP timeout for a single Public API request.
DEFAULT_API_REQUEST_TIMEOUT = 30
CONF_ENABLE_REMOTE_CONTROL = "enable_remote_control"
CONF_ACCEPT_REMOTE_CONTROL_DISCLAIMER = "accept_remote_control_disclaimer"
CONF_ENABLE_ALEXA_SCENES = "enable_alexa_scenes"
CONF_ALEXA_EASY_SETUP = "alexa_easy_setup"
CONF_ALEXA_TARGET_COLLECTIVE = "alexa_target_collective"
CONF_ALEXA_FEED_SCENE_NAME = "alexa_feed_scene_name"
CONF_ALEXA_FEED_SCENE_MODE = "alexa_feed_scene_mode"
CONF_ALEXA_FEED_RETURN_ENABLED = "alexa_feed_return_enabled"
CONF_ALEXA_FEED_RETURN_DELAY_MINUTES = "alexa_feed_return_delay_minutes"
CONF_ALEXA_FEED_RETURN_MODE = "alexa_feed_return_mode"
CONF_ALEXA_MAINT_SCENE_NAME = "alexa_maint_scene_name"
CONF_ALEXA_MAINT_SCENE_MODE = "alexa_maint_scene_mode"
CONF_ALEXA_MAINT_RETURN_ENABLED = "alexa_maint_return_enabled"
CONF_ALEXA_MAINT_RETURN_DELAY_MINUTES = "alexa_maint_return_delay_minutes"
CONF_ALEXA_MAINT_RETURN_MODE = "alexa_maint_return_mode"
CONF_ALEXA_CUSTOM_SCENE_NAME = "alexa_custom_scene_name"
CONF_ALEXA_CUSTOM_SCENE_MODE = "alexa_custom_scene_mode"
CONF_ALEXA_CUSTOM_RETURN_ENABLED = "alexa_custom_return_enabled"
CONF_ALEXA_CUSTOM_RETURN_DELAY_MINUTES = "alexa_custom_return_delay_minutes"
CONF_ALEXA_CUSTOM_RETURN_MODE = "alexa_custom_return_mode"
DEFAULT_REGION = "us-west-2"
DEFAULT_WATCHDOG_INACTIVITY = 5
DEFAULT_COMMAND_CONFIRM_TIMEOUT = 15
DEFAULT_OUTPUT_COMMAND_COOLDOWN_SECONDS = 1.0
DEFAULT_MODE_COMMAND_COOLDOWN_SECONDS = 2.0
DEFAULT_MAX_MANUAL_DOSE_SECONDS = 1800
DEFAULT_AVAILABILITY_WINDOW_SECONDS = 360  # 6 minutes; slightly longer than the 5-minute watchdog
DEFAULT_ENABLE_ALEXA_SCENES = True
DEFAULT_ALEXA_EASY_SETUP = True
DEFAULT_ALEXA_FEED_SCENE_NAME = "Feed Mode"
DEFAULT_ALEXA_FEED_SCENE_MODE = "Feeding"
DEFAULT_ALEXA_FEED_RETURN_ENABLED = True
DEFAULT_ALEXA_FEED_RETURN_DELAY_MINUTES = 15
DEFAULT_ALEXA_FEED_RETURN_MODE = "Normal"
DEFAULT_ALEXA_MAINT_SCENE_NAME = "Maintenance Mode"
DEFAULT_ALEXA_MAINT_SCENE_MODE = "Maintenance"
DEFAULT_ALEXA_MAINT_RETURN_ENABLED = False
DEFAULT_ALEXA_MAINT_RETURN_DELAY_MINUTES = 30
DEFAULT_ALEXA_MAINT_RETURN_MODE = "Normal"
DEFAULT_ALEXA_CUSTOM_SCENE_NAME = ""
DEFAULT_ALEXA_CUSTOM_SCENE_MODE = ""
DEFAULT_ALEXA_CUSTOM_RETURN_ENABLED = False
DEFAULT_ALEXA_CUSTOM_RETURN_DELAY_MINUTES = 15
DEFAULT_ALEXA_CUSTOM_RETURN_MODE = "Normal"

PLATFORMS: list[str] = ["sensor", "binary_sensor", "button", "select", "switch", "number", "scene"]

SIGNAL_COLLECTIVE_UPDATED = "hydros_collective_updated_{entry}_{thing}"
SIGNAL_CONFIG_UPDATED = "hydros_config_updated_{entry}_{thing}"

SERVICE_SET_OUTPUT_STATE = "set_output_state"
SERVICE_SET_PUMP_SPEED = "set_pump_speed"
SERVICE_CHANGE_MODE = "change_mode"
SERVICE_MANUAL_DOSE = "manual_dose"
