DOMAIN = "midea_water_softener"
DEVICE_TYPE = 0xED
QUERY_BODY_TYPE = 0x09
DEFAULT_SCAN_INTERVAL = 30  # seconds

# Config/storage keys
CONF_ACCOUNT = "account"
CONF_PASSWORD = "password"
CONF_SERVER = "server"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_SCAN_INTERVAL = "scan_interval"

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
