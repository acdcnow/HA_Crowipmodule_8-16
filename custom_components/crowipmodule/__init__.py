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
    """Set up the Crow IP Module component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crow IP Module from a config entry."""
    _LOGGER.info("Starting Crow IP Module setup for entry: %s", entry.title)
    
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    keep_alive = entry.data.get(CONF_KEEP_ALIVE, 60)
    connection_timeout = entry.data.get(CONF_TIMEOUT, 10)
    
    _LOGGER.debug("Init params: Host=%s, Port=%s, Timeout=%s", host, port, connection_timeout)
    
    try:
        controller = CrowIPAlarmPanel(
            host, port, "0000", keep_alive, None, connection_timeout
        )
    except Exception as e:
        _LOGGER.error("Failed to initialize CrowIPAlarmPanel object: %s", e)
        return False

    hass.data[DOMAIN][entry.entry_id] = controller

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
        
        # Delayed Refresh Task to fix "Unknown" status on reload/start
        async def delayed_refresh():
            # Wait for the panel to dump its state (usually happens immediately after login)
            _LOGGER.debug("Waiting 2s for data dump from panel...")
            await asyncio.sleep(2.0)
            _LOGGER.info("Forcing entity state update after connection.")
            async_dispatcher_send(hass, SIGNAL_SYSTEM_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_AREA_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_ZONE_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_OUTPUT_UPDATE, None)

        hass.loop.create_task(delayed_refresh())

    def connection_fail_callback(data):
        _LOGGER.warning("Connection lost to Crow IP Module. Reconnecting...")

    controller.callback_zone_state_change = zones_updated_callback
    controller.callback_area_state_change = areas_updated_callback
    controller.callback_system_state_change = system_updated_callback
    controller.callback_output_state_change = output_updated_callback
    controller.callback_connected = connected_callback
    controller.callback_login_timeout = connection_fail_callback

    # Wait for socket cleanup before connecting (Fixes "Unable to connect" on Reload)
    _LOGGER.debug("Waiting 2s for socket cleanup...")
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
    _LOGGER.info("Unloading Crow IP Module entry.")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        controller = hass.data[DOMAIN][entry.entry_id]
        _LOGGER.info("Stopping Crow IP Module connection...")
        await hass.async_add_executor_job(controller.stop)
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
