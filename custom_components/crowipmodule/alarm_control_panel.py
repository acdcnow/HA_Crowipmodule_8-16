"""Support for Crow IP Module Alarm Control Panel."""
import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_AREA_UPDATE,
    SIGNAL_KEYPAD_UPDATE,
    CONF_AREAS,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    options = entry.options
    host = entry.data[CONF_HOST]
    
    configured_areas = options.get(CONF_AREAS, {})
    
    if not configured_areas:
        configured_areas = {
            "1": {"name": "Area 1", "code": "", "code_arm_required": True},
            "2": {"name": "Area 2", "code": "", "code_arm_required": True}
        }

    devices = []
    for area_num_str, area_data in configured_areas.items():
        try:
            area_num = int(area_num_str)
            devices.append(CrowAlarmPanel(
                controller, host,
                area_num, 
                area_data.get("name", f"Area {area_num}"),
                area_data.get("code", ""),
                area_data.get("code_arm_required", True)
            ))
        except ValueError:
            _LOGGER.error("Invalid area number found in config: %s", area_num_str)

    async_add_entities(devices)

class CrowAlarmPanel(AlarmControlPanelEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, controller, host, area_number, name, code, code_required) -> None:
        self._controller = controller
        self._host = host
        self._area_number_int = area_number
        self._area_number = "A" if area_number == 1 else "B"
        
        self._attr_name = name
        self._attr_unique_id = f"crow_area_{area_number}"
        self._attr_icon = "mdi:shield-home"
        
        self._code = code
        self._code_arm_required_config = code_required
        
        self._info = controller.area_state.get(area_number, {"status": {}})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._host}",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_AREA_UPDATE, self._update_callback)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_KEYPAD_UPDATE, self._update_callback)
        )

    @callback
    def _update_callback(self, area) -> None:
        if area is None or area == self._area_number:
            if self._area_number_int in self._controller.area_state:
                self._info = self._controller.area_state[self._area_number_int]
            self.async_write_ha_state()

    @property
    def code_format(self) -> CodeFormat | None:
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        if self._code:
            return False
        return self._code_arm_required_config

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        return (
            AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.TRIGGER
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        _LOGGER.info("Sending DISARM command to Area %s", self._area_number)
        code_to_use = str(code) if code else str(self._code)
        try:
            self._controller.disarm(code_to_use)
        except Exception as e:
             _LOGGER.error("Error sending disarm command: %s", e)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        _LOGGER.info("Sending ARM STAY command to Area %s", self._area_number)
        try:
            self._controller.arm_stay()
            code_to_use = str(code) if code else str(self._code)
            if code_to_use:
                self._controller.send_keypress(code_to_use)
        except Exception as e:
             _LOGGER.error("Error sending arm home command: %s", e)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        _LOGGER.info("Sending ARM AWAY command to Area %s", self._area_number)
        try:
            self._controller.arm_away()
            code_to_use = str(code) if code else str(self._code)
            if code_to_use:
                self._controller.send_keypress(code_to_use)
        except Exception as e:
             _LOGGER.error("Error sending arm away command: %s", e)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        _LOGGER.warning("Sending PANIC TRIGGER to Area %s", self._area_number)
        try:
            self._controller.panic_alarm("")
        except Exception as e:
            _LOGGER.error("Error triggering panic: %s", e)

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        status = self._info.get("status", {})
        if status.get("alarm"): return AlarmControlPanelState.TRIGGERED
        if status.get("armed"): return AlarmControlPanelState.ARMED_AWAY
        if status.get("stay_armed"): return AlarmControlPanelState.ARMED_HOME
        if status.get("exit_delay") or status.get("stay_exit_delay"): return AlarmControlPanelState.ARMING
        if status.get("disarmed"): return AlarmControlPanelState.DISARMED
        return None
    
    @property
    def extra_state_attributes(self):
        return self._info.get("status", {})
