"""Crow/AAP IP Module init file."""
import asyncio
import logging
import voluptuous as vol

from pycrowipmodule import CrowIPAlarmPanel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST, CONF_PORT, CONF_TIMEOUT, EVENT_HOMEASSISTANT_STOP, Platform
)
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN, CONF_KEEP_ALIVE,
    SIGNAL_ZONE_UPDATE, SIGNAL_AREA_UPDATE, 
    SIGNAL_SYSTEM_UPDATE, SIGNAL_OUTPUT_UPDATE
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Crow IP Module component from YAML (legacy)."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crow IP Module from a config entry."""
    _LOGGER.info("Starting Crow IP Module setup for entry: %s", entry.title)
    
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    keep_alive = entry.data.get(CONF_KEEP_ALIVE, 60)
    connection_timeout = entry.data.get(CONF_TIMEOUT, 10)
    
    _LOGGER.debug("Init params: Host=%s, Port=%s, Timeout=%s, KeepAlive=%s", 
                  host, port, connection_timeout, keep_alive)
    
    try:
        controller = CrowIPAlarmPanel(
            host, port, "0000", keep_alive, None, connection_timeout
        )
    except Exception as e:
        _LOGGER.error("Failed to initialize CrowIPAlarmPanel object: %s", e)
        return False

    hass.data[DOMAIN][entry.entry_id] = controller

    # Thread-safe Dispatchers
    def _thread_safe_send(signal, data):
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, signal, data)

    def zones_updated_callback(data):
        _thread_safe_send(SIGNAL_ZONE_UPDATE, data)

    def areas_updated_callback(data):
        _thread_safe_send(SIGNAL_AREA_UPDATE, data)

    def system_updated_callback(data):
        _thread_safe_send(SIGNAL_SYSTEM_UPDATE, data)

    def output_updated_callback(data):
        _thread_safe_send(SIGNAL_OUTPUT_UPDATE, data)

    def connected_callback(data):
        _LOGGER.info("Successfully connected to Crow IP Module at %s", host)
        
        # ASYNC REFRESH TASK
        # This is crucial for BOTH Boot and Reload.
        # When we connect, the memory is empty. The panel sends a dump.
        # We wait 2s for the dump to arrive, then force all entities to read the new state.
        async def delayed_initial_refresh():
            _LOGGER.debug("Connection established. Waiting 2.0s for system status dump...")
            await asyncio.sleep(2.0)
            
            _LOGGER.info("Processing initial system state (Force Refresh)...")
            async_dispatcher_send(hass, SIGNAL_SYSTEM_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_AREA_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_ZONE_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_OUTPUT_UPDATE, None)
            _LOGGER.debug("Initial state refresh dispatched.")

        # Schedule the task on the event loop so it doesn't block
        hass.loop.create_task(delayed_initial_refresh())

    def connection_fail_callback(data):
        _LOGGER.warning("Connection lost to Crow IP Module at %s. Waiting for reconnect...", host)

    # Register callbacks
    controller.callback_zone_state_change = zones_updated_callback
    controller.callback_area_state_change = areas_updated_callback
    controller.callback_system_state_change = system_updated_callback
    controller.callback_output_state_change = output_updated_callback
    controller.callback_connected = connected_callback
    controller.callback_login_timeout = connection_fail_callback

    # Wait for previous socket cleanup (prevents 'Unable to connect' on Reload)
    # This delay happens before we even try to open the socket.
    _LOGGER.debug("Waiting 2 seconds before starting connection thread to ensure socket cleanup...")
    await asyncio.sleep(2.0)

    _LOGGER.info("Starting CrowIpModule background thread...")
    try:
        hass.async_add_executor_job(controller.start)
    except Exception as e:
         _LOGGER.error("Fatal error starting controller thread: %s", e)
         return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: controller.stop())
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Crow IP Module entry.")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        controller = hass.data[DOMAIN][entry.entry_id]
        _LOGGER.info("Stopping Crow IP Module connection...")
        await hass.async_add_executor_job(controller.stop)
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
