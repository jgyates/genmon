"""Constants for the Genmon Generator Monitor integration."""

DOMAIN = "genmon"

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "button",
    "switch",
    "select",
    "number",
]

# Config flow
CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_USE_SSL = "use_ssl"

DEFAULT_PORT = 9083
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_USE_SSL = True

# Options
CONF_SCAN_INTERVAL = "scan_interval"
CONF_BLACKLIST = "blacklist"
CONF_BUTTON_PASSCODE = "button_passcode"
CONF_INCLUDE_MONITOR_STATS = "include_monitor_stats"
CONF_INCLUDE_WEATHER = "include_weather"

# Device class / unit mappings for value extraction
UNIT_STRIP_PATTERNS = {
    " V": "V",
    " A": "A",
    " W": "W",
    " kW": "kW",
    " Hz": "Hz",
    " RPM": "RPM",
    " C": "°C",
    " F": "°F",
    " %": "%",
    " gal": "gal",
    " hours": "h",
}

# Genmon path separator
PATH_SEP = "/"
