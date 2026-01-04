"""Support for Crow Alarm IP Module Binary Sensors."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.core import callback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN, SIGNAL_ZONE_UPDATE, SIGNAL_SYSTEM_UPDATE,
    CONF_ZONES, 
    CONF_FW_VERSION, CONF_FW_DATE, 
    DEFAULT_FW_VERSION, DEFAULT_FW_DATE,
    # System Sensors
    CONF_OBJ_MAINS, CONF_OBJ_BATTERY, CONF_OBJ_TAMPER, 
    CONF_OBJ_LINE, CONF_OBJ_DIALLER, CONF_OBJ_ZONE_BATTERY
)

# Zusätzliche Konstanten für System Sensoren
CONF_OBJ_FUSE = "fuse"
CONF_OBJ_PENDANT_BATTERY = "pendantbattery"
CONF_OBJ_CODE_TAMPER = "codetamper"
CONF_OBJ_READY = "ready"

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    _LOGGER.debug("Setting up Binary Sensors...")
    controller = hass.data[DOMAIN][entry.entry_id]
    options = entry.options
    host = entry.data[CONF_HOST]
    
    fw_version = entry.data.get(CONF_FW_VERSION, DEFAULT_FW_VERSION)
    fw_date = entry.data.get(CONF_FW_DATE, DEFAULT_FW_DATE)
    
    entities = []

    # BLOCK 1: Hauptsensoren (Zonen Öffnung)
    configured_zones = options.get(CONF_ZONES, {})
    if not configured_zones:
        for i in range(1, 17):
            configured_zones[str(i)] = {"name": f"Zone {i}", "type": "window"}

    sorted_zone_ids = sorted([int(k) for k in configured_zones.keys()])

    for zone_num in sorted_zone_ids:
        zone_info = configured_zones[str(zone_num)]
        entities.append(CrowZoneSensor(
            controller, host, zone_num, zone_info["name"], zone_info["type"], "open", fw_version, fw_date
        ))

    # BLOCK 2: System Sensoren
    system_sensors = [
        (CONF_OBJ_MAINS, "Mains Power", BinarySensorDeviceClass.POWER, False),
        (CONF_OBJ_BATTERY, "System Battery", BinarySensorDeviceClass.BATTERY, True),
        (CONF_OBJ_TAMPER, "System Tamper", BinarySensorDeviceClass.TAMPER, False),
        (CONF_OBJ_LINE, "Phone Line", BinarySensorDeviceClass.CONNECTIVITY, False),
        (CONF_OBJ_DIALLER, "Dialler", BinarySensorDeviceClass.CONNECTIVITY, False),
        (CONF_OBJ_ZONE_BATTERY, "Zone Battery", BinarySensorDeviceClass.BATTERY, True),
        (CONF_OBJ_FUSE, "System Fuse", BinarySensorDeviceClass.PROBLEM, True),
        (CONF_OBJ_PENDANT_BATTERY, "Pendant Battery", BinarySensorDeviceClass.BATTERY, True),
        (CONF_OBJ_CODE_TAMPER, "Keypad Tamper (Code)", BinarySensorDeviceClass.TAMPER, False),
        (CONF_OBJ_READY, "Ready to Arm", BinarySensorDeviceClass.RUNNING, False),
    ]
    for key, name, dev_class, invert_logic in system_sensors:
        entities.append(CrowSystemStatusSensor(controller, host, key, name, dev_class, invert_logic, fw_version, fw_date))

    # BLOCK 3: Zone Tamper
    for zone_num in sorted_zone_ids:
        zone_info = configured_zones[str(zone_num)]
        entities.append(CrowZoneSensor(
            controller, host, zone_num, f"{zone_info['name']} Tamper", BinarySensorDeviceClass.TAMPER, "tamper", fw_version, fw_date
        ))

    # BLOCK 4: Zone Bypass
    for zone_num in sorted_zone_ids:
        zone_info = configured_zones[str(zone_num)]
        entities.append(CrowZoneSensor(
            controller, host, zone_num, f"{zone_info['name']} Bypass", BinarySensorDeviceClass.SAFETY, "bypass", fw_version, fw_date
        ))

    async_add_entities(entities)

class CrowBaseEntity(BinarySensorEntity):
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
            sw_version=self._fw_string,
            configuration_url=f"http://{self._host}",
        )

class CrowZoneSensor(CrowBaseEntity):
    def __init__(self, controller, host, zone_number, zone_name, device_class, attribute_key, fw_version, fw_date):
        super().__init__(controller, host, fw_version, fw_date)
        self._zone_number = zone_number
        self._attr_name = zone_name
        self._attr_device_class = device_class
        self._attribute_key = attribute_key
        
        self._attr_unique_id = f"crow_zone_{zone_number}_{attribute_key}"
        
        # FIX: Verwende DIAGNOSTIC statt CONFIG
        if attribute_key == "open":
             self._attr_entity_category = None 
        else:
             self._attr_entity_category = EntityCategory.DIAGNOSTIC

        self._info = controller.zone_state.get(zone_number, {"status": {}})

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_ZONE_UPDATE, self._update_callback)
        )

    @property
    def is_on(self):
        if not self._info or "status" not in self._info:
            return False
        return self._info["status"].get(self._attribute_key, False)

    @property
    def extra_state_attributes(self):
        return self._info.get("status", {})

    @callback
    def _update_callback(self, zone):
        if zone is None or int(zone) == self._zone_number:
            if self._zone_number in self._controller.zone_state:
                self._info = self._controller.zone_state[self._zone_number]
            self.async_write_ha_state()

class CrowSystemStatusSensor(CrowBaseEntity):
    def __init__(self, controller, host, key, name, device_class, invert_logic, fw_version, fw_date):
        super().__init__(controller, host, fw_version, fw_date)
        self._key = key
        self._attr_name = name
        self._attr_device_class = device_class
        self._invert_logic = invert_logic
        self._attr_unique_id = f"crow_sys_{key}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SYSTEM_UPDATE, self._update_callback)
        )

    @property
    def is_on(self):
        status = self._controller.system_state.get("status", {})
        val = status.get(self._key, True) 
        if self._invert_logic:
            return not val
        return val

    @callback
    def _update_callback(self, _):
        self.async_write_ha_state()