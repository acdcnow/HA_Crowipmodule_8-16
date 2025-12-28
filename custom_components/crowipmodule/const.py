"""Constants for the Crow IP Module integration."""

DOMAIN = "crowipmodule"

# Configuration Keys
CONF_KEEP_ALIVE = "keepalive_interval"
CONF_AREAS = "areas"
CONF_ZONES = "zones"
CONF_OUTPUTS = "outputs"

# Dynamic Configuration Keys for Counts
CONF_NUM_AREAS = "number_of_areas"
CONF_NUM_ZONES = "number_of_zones"

# Limits
MAX_AREAS = 2
MAX_ZONES = 16 
DEFAULT_NUM_AREAS = 2
DEFAULT_NUM_ZONES = 8

# Defaults
DEFAULT_PORT = 5002
DEFAULT_TIMEOUT = 10
DEFAULT_KEEPALIVE = 60

# Signals
SIGNAL_ZONE_UPDATE = "crowipmodule.zones_updated"
SIGNAL_AREA_UPDATE = "crowipmodule.areas_updated"
SIGNAL_SYSTEM_UPDATE = "crowipmodule.system_updated"
SIGNAL_OUTPUT_UPDATE = "crowipmodule.output_updated"
SIGNAL_KEYPAD_UPDATE = "crowipmodule.keypad_updated"

# System status sensors keys
CONF_OBJ_MAINS = "mains"
CONF_OBJ_BATTERY = "battery"
CONF_OBJ_TAMPER = "tamper"
CONF_OBJ_LINE = "line"
CONF_OBJ_DIALLER = "dialler"
CONF_OBJ_ZONE_BATTERY = "zonebattery"
