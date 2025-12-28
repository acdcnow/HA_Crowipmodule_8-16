"""Config flow for Crow IP Module integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_KEEPALIVE,
    CONF_KEEP_ALIVE,
    CONF_AREAS,
    CONF_ZONES,
    CONF_OUTPUTS,
    CONF_NUM_AREAS,
    CONF_NUM_ZONES,
    MAX_AREAS,
    MAX_ZONES,
    DEFAULT_NUM_AREAS,
    DEFAULT_NUM_ZONES,
)

_LOGGER = logging.getLogger(__name__)

# Set "window" as the first element to make it default if not specified otherwise logic
ZONE_TYPES = [
    "window", "motion", "door", "smoke", "gas", "co", "tamper", "safety"
]

PAGE_SIZE = 4

class CrowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crow IP Module."""

    VERSION = 1

    def __init__(self):
        self._data = {}
        self._options = {}
        self._zone_page = 0

    async def async_step_user(self, user_input=None):
        """Step 1: Connection details and counts."""
        errors = {}
        if user_input is not None:
            _LOGGER.info("User started config flow setup.")
            self._data = user_input
            self._options[CONF_AREAS] = {}
            self._options[CONF_OUTPUTS] = {}
            self._options[CONF_ZONES] = {}
            
            unique_id = f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            
            return await self.async_step_areas()

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_KEEP_ALIVE, default=DEFAULT_KEEPALIVE): int,
            vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
            vol.Required(CONF_NUM_AREAS, default=DEFAULT_NUM_AREAS): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_AREAS)),
            vol.Required(CONF_NUM_ZONES, default=DEFAULT_NUM_ZONES): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_ZONES)),
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_areas(self, user_input=None):
        """Step 2: Configure Areas."""
        count = self._data.get(CONF_NUM_AREAS, DEFAULT_NUM_AREAS)
        
        if user_input is not None:
            areas_config = {}
            for i in range(1, count + 1):
                areas_config[str(i)] = {
                    "name": user_input.get(f"area_{i}_name"), 
                    "code": user_input.get(f"area_{i}_code", ""), 
                    "code_arm_required": True
                }
            self._options[CONF_AREAS] = areas_config
            return await self.async_step_outputs()

        schema = {}
        for i in range(1, count + 1):
            schema[vol.Required(f"area_{i}_name", default=f"Area {i}")] = str
            schema[vol.Optional(f"area_{i}_code", default="")] = str

        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))

    async def async_step_outputs(self, user_input=None):
        """Step 3: Configure Outputs."""
        if user_input is not None:
            outputs_config = {}
            for i in range(1, 3):
                name = user_input.get(f"output_{i}_name")
                if name:
                    outputs_config[str(i)] = {"name": name}
            
            self._options[CONF_OUTPUTS] = outputs_config
            self._zone_page = 0
            return await self.async_step_zones()

        schema = {}
        for i in range(1, 3):
            default_name = f"Output {i}"
            schema[vol.Optional(f"output_{i}_name", description={"suggested_value": default_name})] = str

        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        """Step 4: Configure Zones (Paginated)."""
        count = self._data.get(CONF_NUM_ZONES, DEFAULT_NUM_ZONES)
        
        if user_input is not None:
            for key, value in user_input.items():
                if key.startswith("zone_") and key.endswith("_name"):
                    idx = key.split("_")[1]
                    if idx not in self._options[CONF_ZONES]:
                        self._options[CONF_ZONES][idx] = {}
                    self._options[CONF_ZONES][idx]["name"] = value
                elif key.startswith("zone_") and key.endswith("_type"):
                    idx = key.split("_")[1]
                    if idx not in self._options[CONF_ZONES]:
                        self._options[CONF_ZONES][idx] = {}
                    self._options[CONF_ZONES][idx]["type"] = value
            self._zone_page += 1

        start_idx = self._zone_page * PAGE_SIZE + 1
        if start_idx > count:
            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
                options=self._options
            )

        end_idx = min(start_idx + PAGE_SIZE - 1, count)
        schema = {}
        for i in range(start_idx, end_idx + 1):
            # Default to 'window' if new
            schema[vol.Optional(f"zone_{i}_name")] = str
            schema[vol.Optional(f"zone_{i}_type", default="window")] = vol.In(ZONE_TYPES)

        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))

    async def async_step_import(self, import_data):
        """Handle import from YAML."""
        data = {
            CONF_HOST: import_data.get(CONF_HOST),
            CONF_PORT: import_data.get(CONF_PORT, DEFAULT_PORT),
            CONF_KEEP_ALIVE: import_data.get(CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE),
            CONF_TIMEOUT: import_data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            CONF_NUM_AREAS: DEFAULT_NUM_AREAS,
            CONF_NUM_ZONES: DEFAULT_NUM_ZONES,
        }
        options = {
            CONF_AREAS: {},
            CONF_OUTPUTS: {},
            CONF_ZONES: {}
        }
        options[CONF_AREAS]["1"] = {"name": "Area 1", "code": "", "code_arm_required": True}
        options[CONF_AREAS]["2"] = {"name": "Area 2", "code": "", "code_arm_required": True}
        options[CONF_OUTPUTS]["1"] = {"name": "Output 1"}
        options[CONF_OUTPUTS]["2"] = {"name": "Output 2"}
        
        unique_id = f"{data[CONF_HOST]}_{data[CONF_PORT]}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=data[CONF_HOST], data=data, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CrowOptionsFlowHandler(config_entry)


class CrowOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry
        self._temp_data = {}
        self._temp_options = {}
        self._zone_page = 0

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self._temp_data = user_input
            return await self.async_step_areas()

        data = self._config_entry.data
        options = self._config_entry.options
        
        # Load existing counts to pre-fill
        c_areas = data.get(CONF_NUM_AREAS, len(options.get(CONF_AREAS, {})) or DEFAULT_NUM_AREAS)
        c_zones = data.get(CONF_NUM_ZONES, len(options.get(CONF_ZONES, {})) or DEFAULT_NUM_ZONES)
        
        # Ensure minimums
        c_areas = max(1, min(c_areas, MAX_AREAS))
        c_zones = max(1, min(c_zones, MAX_ZONES))

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=data.get(CONF_HOST)): str,
            vol.Optional(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_KEEP_ALIVE, default=data.get(CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE)): int,
            vol.Optional(CONF_TIMEOUT, default=data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)): int,
            vol.Required(CONF_NUM_AREAS, default=c_areas): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_AREAS)),
            vol.Required(CONF_NUM_ZONES, default=c_zones): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_ZONES)),
        })

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_areas(self, user_input=None):
        count = self._temp_data.get(CONF_NUM_AREAS, DEFAULT_NUM_AREAS)
        if user_input is not None:
            self._temp_options[CONF_AREAS] = {}
            for i in range(1, count + 1):
                self._temp_options[CONF_AREAS][str(i)] = {
                    "name": user_input.get(f"area_{i}_name"),
                    "code": user_input.get(f"area_{i}_code", ""),
                    "code_arm_required": True
                }
            return await self.async_step_outputs()

        existing = self._config_entry.options.get(CONF_AREAS, {})
        schema = {}
        for i in range(1, count + 1):
            d = existing.get(str(i), {})
            schema[vol.Optional(f"area_{i}_name", default=d.get("name", f"Area {i}"))] = str
            schema[vol.Optional(f"area_{i}_code", default=d.get("code", ""))] = str
        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))

    async def async_step_outputs(self, user_input=None):
        if user_input is not None:
            self._temp_options[CONF_OUTPUTS] = {}
            for i in range(1, 3):
                name = user_input.get(f"output_{i}_name")
                if name:
                    self._temp_options[CONF_OUTPUTS][str(i)] = {"name": name}
            
            self._zone_page = 0
            self._temp_options[CONF_ZONES] = {}
            return await self.async_step_zones()

        existing = self._config_entry.options.get(CONF_OUTPUTS, {})
        schema = {}
        for i in range(1, 3):
            d = existing.get(str(i), {})
            default = d.get("name", "")
            if not default: default = f"Output {i}"
            schema[vol.Optional(f"output_{i}_name", description={"suggested_value": default})] = str
        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        count = self._temp_data.get(CONF_NUM_ZONES, DEFAULT_NUM_ZONES)
        
        if user_input is not None:
            for key, value in user_input.items():
                if key.startswith("zone_") and key.endswith("_name"):
                    idx = key.split("_")[1]
                    if idx not in self._temp_options[CONF_ZONES]:
                        self._temp_options[CONF_ZONES][idx] = {}
                    self._temp_options[CONF_ZONES][idx]["name"] = value
                elif key.startswith("zone_") and key.endswith("_type"):
                    idx = key.split("_")[1]
                    if idx not in self._temp_options[CONF_ZONES]:
                        self._temp_options[CONF_ZONES][idx] = {}
                    self._temp_options[CONF_ZONES][idx]["type"] = value
            self._zone_page += 1

        start_idx = self._zone_page * PAGE_SIZE + 1
        
        if start_idx > count:
            new_data = self._config_entry.data.copy()
            new_data.update(self._temp_data)
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data, options=self._temp_options)
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        existing_zones = self._config_entry.options.get(CONF_ZONES, {})
        end_idx = min(start_idx + PAGE_SIZE - 1, count)
        
        schema = {}
        for i in range(start_idx, end_idx + 1):
            d = existing_zones.get(str(i), {})
            current_name = d.get("name", "")
            current_type = d.get("type", "window") # Set default window here as well if not set
            
            schema[vol.Optional(f"zone_{i}_name", description={"suggested_value": current_name})] = str
            schema[vol.Optional(f"zone_{i}_type", default=current_type)] = vol.In(ZONE_TYPES)

        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))
