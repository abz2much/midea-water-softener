DOMAIN = "midea_water_softener"
DEVICE_TYPE = 0xED
QUERY_BODY_TYPE = 0x09  # expected body[0] in the *response* (used in parse_response)
DEFAULT_SCAN_INTERVAL = 30  # seconds

# Config/storage keys
CONF_ACCOUNT = "account"
CONF_PASSWORD = "password"
CONF_SERVER = "server"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_MODEL = "model"
CONF_SERIAL_NUMBER = "serial_number"
CONF_SCAN_INTERVAL = "scan_interval"
# Local (LAN) control. All three must be set, or the integration is cloud only.
CONF_HOST = "host"
CONF_TOKEN = "token"
CONF_KEY = "key"

# Anti-leakage limit (set command 0x010A).
# UNCONFIRMED: the unit of the "addition" field when setting the limit. The status
# byte is in units of 10 L (Lua:416) and the Lua writes the same property back with
# no scaling, so 10 L is assumed here. Needs a real-device test before release.
LEAK_LIMIT_SET_UNIT_L = 10
# The Lua states no range or step. These are our own limits. The maximum is the
# most the status can read back: the status byte holds the limit in units of
# 10 L, and one byte tops out at 255 * 10 = 2550 L.
LEAK_LIMIT_MIN_L = 10
LEAK_LIMIT_MAX_L = 2550
LEAK_LIMIT_STEP_L = 10

# Server options presented in config flow
SERVERS = {
    "MSmartHome (Global)": "https://mp-prod.appsmb.com/mas/v5/app/proxy?alias=",
}

# Device attribute keys — shared across all platform files
ATTR_SOFT_WATER_REMAINING = "soft_water_remaining"
ATTR_FLOW_RATE = "flow_rate"
ATTR_SALT_REMAINING = "salt_remaining"
ATTR_DEVICE_STATUS = "device_status"
ATTR_WATER_CONSUMPTION_TOTAL = "water_consumption_total"
ATTR_USE_DAYS = "use_days"
ATTR_REGEN_SECONDS_REMAINING = "regen_seconds_remaining"
ATTR_SOFTEN = "soften"
ATTR_INLET = "inlet"
ATTR_ANTI_LEAKAGE = "anti_leakage"
ATTR_LEAK_THRESHOLD = "leak_threshold"
ATTR_LEAK_DETECTED = "leak_detected"
ATTR_HARDNESS = "hardness"
ATTR_REGEN_INTERVAL = "regen_interval"
ATTR_REGEN_HOUR = "regen_hour"
ATTR_REGEN_MIN = "regen_min"
ATTR_REGENERATING = "regenerating"
ATTR_STANDBY = "standby"
ATTR_ERROR = "error"

# Device status strings
STATUS_STANDBY = "standby"
STATUS_REGENERATING = "regenerating"
STATUS_NORMAL = "normal"
