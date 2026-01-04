"""Support for Crow IP Module text sensors."""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_SYSTEM_UPDATE,
    SIGNAL_AREA_UPDATE,
    CONF_FW_VERSION, CONF_FW_DATE, 
    DEFAULT_FW_VERSION, DEFAULT_FW_DATE
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Crow IP Module sensor."""
    controller = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    
    # Firmware Infos laden
    fw_version = entry.data.get(CONF_FW_VERSION, DEFAULT_FW_VERSION)
    fw_date = entry.data.get(CONF_FW_DATE, DEFAULT_FW_DATE)
    
    _LOGGER.info("Setting up Crow Text Sensors")
    
    entities = [
        CrowSystemSensor(controller, host, fw_version, fw_date),
        CrowAlarmZoneSensor(controller, host, 1, "Area A Last Alarm", fw_version, fw_date),
        CrowAlarmZoneSensor(controller, host, 2, "Area B Last Alarm", fw_version, fw_date),
    ]
    
    async_add_entities(entities, True)


class CrowBaseTextSensor(SensorEntity):
    _attr_has_entity_name = True
    
    def __init__(self, controller, host, fw_version, fw_date):
        self._controller = controller
        self._host = host
        self._fw_string = f"{fw_version} ({fw_date})"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            sw_version=self._fw_string, # Konsistente Version
            configuration_url=f"http://{self._host}",
        )

class CrowSystemSensor(CrowBaseTextSensor):
    """Representation of the Crow Alarm System Status Text."""
    
    def __init__(self, controller, host, fw_version, fw_date) -> None:
        super().__init__(controller, host, fw_version, fw_date)
        self._attr_name = "System Status"
        self._attr_unique_id = "crow_system_status_text"
        self._attr_icon = "mdi:shield-home"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._info = controller.system_state

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SYSTEM_UPDATE, self._update_callback)
        )

    @property
    def native_value(self) -> str:
        status = self._info.get("status", {})
        if not status: return "Ready"
        
        if status.get("alarm"): return "ALARM"
        if status.get("armed"): return "Armed Away"
        if status.get("stay_armed"): return "Armed Stay"
        if status.get("exit_delay"): return "Exit Delay"
        if status.get("stay_exit_delay"): return "Stay Exit Delay"
        if not status.get("mains", True): return "Power Failure"
        if not status.get("battery", True): return "Low Battery"
            
        return "Ready"

    @callback
    def _update_callback(self, system) -> None:
        self._info = self._controller.system_state
        self.async_write_ha_state()

class CrowAlarmZoneSensor(CrowBaseTextSensor):
    """Zeigt an, welche Zone zuletzt Alarm ausgelöst hat."""

    def __init__(self, controller, host, area_num, name, fw_version, fw_date) -> None:
        super().__init__(controller, host, fw_version, fw_date)
        self._area_num = area_num
        self._attr_name = name
        self._attr_unique_id = f"crow_alarm_zone_area_{area_num}"
        self._attr_icon = "mdi:alert-circle-check-outline"
        
    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_AREA_UPDATE, self._update_callback)
        )

    @property
    def native_value(self) -> str:
        area = self._controller.area_state.get(self._area_num, {})
        status = area.get("status", {})
        alarm_zone = status.get("alarm_zone", "")
        
        if alarm_zone:
            return f"Zone {alarm_zone}"
        return "None"

    @callback
    def _update_callback(self, area) -> None:
        target_area = "A" if self._area_num == 1 else "B"
        if area is None or area == target_area:
            self.async_write_ha_state()