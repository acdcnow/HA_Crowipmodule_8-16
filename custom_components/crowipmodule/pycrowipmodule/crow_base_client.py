''' Crow/AAP Alarm IP Module Base Connection'''
import asyncio
import logging
import re
import time
from asyncio import ensure_future

from pycrowipmodule import StatusState
from pycrowipmodule.crow_defs import *

_LOGGER = logging.getLogger(__name__)

class CrowIPModuleClient(asyncio.Protocol):

    """Abstract base class for the Crow/AAP IP Module"""
    def __init__(self, panel, loop):
        self._connected = False
        self._alarmPanel = panel

        if loop is None:
            _LOGGER.info("Creating own event loop...")
            self._eventLoop = asyncio.new_event_loop()
            self._ownLoop = True
        else:
            _LOGGER.info("Latching onto existing event loop...")
            self._eventLoop = loop
            self._ownLoop = False

        self._transport = None
        self._shutdown = False
        self._cachedCode = None

        # Streaming buffer for incomplete TCP packets
        self._buffer = b""

        # Heartbeat, throttling, and watchdog state
        self._last_rx_time = time.monotonic()
        self._last_tx_time = 0.0
        self._last_keepalive_sent = 0.0
        self._min_tx_interval = 0.25  # Minimum 250ms spacing between outgoing commands
        self._watchdog_timeout = 25.0  # Seconds to wait for response after STATUS ping
        self._keepalive_task = None
        self._connect_task = None

    def start(self):
        """Public method for initiating connectivity with the Module"""
        _LOGGER.info("Client Start requested")
        self._shutdown = False
        self._last_rx_time = time.monotonic()
        self._connect_task = ensure_future(self.connect(), loop=self._eventLoop)
        self._keepalive_task = ensure_future(self.keep_alive(), loop=self._eventLoop)

        if self._ownLoop:
            _LOGGER.info("Starting up our own event loop...")
            try:
                self._eventLoop.run_forever()
            finally:
                try:
                    pending = asyncio.all_tasks(self._eventLoop)
                    for task in pending:
                        task.cancel()
                except Exception:
                    pass
                self._eventLoop.close()
                _LOGGER.info("Connection shut down and event loop closed cleanly!")

    def stop(self):
        """Public method for shutting down connectivity with the Crow IP Module."""
        _LOGGER.info("Client Stop requested. Disconnecting and cleaning up...")
        self._connected = False
        self._shutdown = True

        # Explicitly close transport to release socket at OS level
        self.disconnect()

        # Cancel pending asyncio tasks
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()

        if self._ownLoop:
            _LOGGER.info("Shutting down Crow IP Module client connection loop...")
            self._eventLoop.call_soon_threadsafe(self._eventLoop.stop)
        else:
            _LOGGER.info("An event loop was given to us - tasks cancelled.")

    async def connect(self):
        """Internal method for making the physical connection."""
        _LOGGER.info(f"Starting connection to Crow IP Module at {self._alarmPanel.host}:{self._alarmPanel.port}")
        
        factory = lambda: self
        
        coro = self._eventLoop.create_connection(factory, self._alarmPanel.host, self._alarmPanel.port)
        try:
            await asyncio.wait_for(coro, timeout=self._alarmPanel.connection_timeout)
        except Exception as e:
            _LOGGER.warning(f'Timeout or error connecting to Crow IP module ({self._alarmPanel.host}:{self._alarmPanel.port}): {e}')
            self.handle_connect_failure()

    def connection_made(self, transport):
        """asyncio callback for a successful connection."""
        _LOGGER.info(f"Connection successfully made to Crow IP Module at {self._alarmPanel.host}:{self._alarmPanel.port}!")
        self._transport = transport
        self._connected = True
        self._buffer = b""
        self._last_rx_time = time.monotonic()
        self._last_keepalive_sent = 0.0
      
        _LOGGER.debug("Invoking callback_connected(True)")
        self._alarmPanel.callback_connected(self._connected)
        if self._connected:
            _LOGGER.info("Requesting initial STATUS dump from panel...")
            self.send_command('status', '')
        
    def connection_lost(self, exc):
        """asyncio callback for connection lost."""
        if exc:
            _LOGGER.warning(f"Connection lost to Crow IP Module. Exception: {exc}")
        else:
            _LOGGER.info("Connection to Crow IP Module closed cleanly.")
        self._connected = False
        self._transport = None
        self._buffer = b""
        self._last_keepalive_sent = 0.0
        if not self._shutdown:
            _LOGGER.info(f"Scheduling reconnection in {self._alarmPanel.connection_timeout}s...")
            ensure_future(self.reconnect(self._alarmPanel.connection_timeout), loop=self._eventLoop)

    async def reconnect(self, delay):
        """Internal method for reconnecting."""
        _LOGGER.info(f"Reconnecting to Crow IP Module in {delay} seconds...")
        self.disconnect()
        await asyncio.sleep(delay)
        if not self._shutdown:
            await self.connect()
           
    def disconnect(self):
        """Internal method for forcing connection closure if hung."""
        _LOGGER.debug('Disconnecting transport...')
        if self._transport:
            try:
                self._transport.close()
            except Exception as err:
                _LOGGER.debug(f"Error closing transport: {err}")
            self._transport = None
        self._buffer = b""
            
    def send_data(self, data):
        """Raw data send - rate-limited to avoid overwhelming the 9600-baud microcontroller."""
        if not self._transport:
            _LOGGER.warning('Cannot send data: no active transport (not yet connected or reconnecting).')
            return

        # Command rate-limiting: enforce minimum delay between commands
        now = time.monotonic()
        elapsed = now - self._last_tx_time
        if elapsed < self._min_tx_interval:
            time.sleep(self._min_tx_interval - elapsed)

        raw_bytes = (data + '\r\n').encode('ascii')
        _LOGGER.debug(f'TX RAW: {raw_bytes}')
        self._last_tx_time = time.monotonic()
        try:
            self._transport.write(raw_bytes)
        except Exception as err:
            _LOGGER.error(f'Failed to send. Reconnecting. Error: {err}')
            self._connected = False
            if not self._shutdown:
                ensure_future(self.reconnect(self._alarmPanel.connection_timeout), loop=self._eventLoop)

    def send_command(self, code, data):
        """Send a command in the proper format."""
        _LOGGER.debug(f"Preparing command: Code={code}, Data={data}")
        if data == '':
            to_send = COMMANDS[code] + ' '
        else:
            if COMMANDS[code] == 'OO':
                to_send = COMMANDS[code] + data
            else:
                to_send = COMMANDS[code] + ' ' + data
        self.send_data(to_send)

    def data_received(self, data):
        """asyncio callback for any data received from the Module. Buffers incomplete lines."""
        if not data:
            return

        self._last_rx_time = time.monotonic()
        self._buffer += data

        # Process all complete lines delimited by newline (\n)
        while b'\n' in self._buffer:
            line_bytes, self._buffer = self._buffer.split(b'\n', 1)
            line_str = line_bytes.decode('latin1', errors='ignore').strip()
            if not line_str:
                continue

            _LOGGER.debug(f"RX LINE: '{line_str}'")

            parsed = self.parseHandler(line_str)
            if not parsed:
                continue

            result = ''
            try:
                _LOGGER.debug(f"Calling handler: {parsed['handler']} | Name: {parsed['name']} | Data: {parsed['data']}")
                handlerFunc = getattr(self, parsed['handler'])
                result = handlerFunc(parsed)
            except (AttributeError, TypeError, KeyError) as err:
                _LOGGER.error(f"Error calling handler func: {err}")

            try:
                _LOGGER.debug(f"Invoking callback: {parsed['callback']} with result: {result}")
                callbackFunc = getattr(self._alarmPanel, parsed['callback'])
                callbackFunc(result)
            except (AttributeError, TypeError, KeyError) as err:
                _LOGGER.debug(f"No callback configured or error invoking it: {err}")

    def parseHandler(self, rawInput):
        """When the Module contacts us - parse out message and data."""
        result = {}
        if rawInput != '':
            match_found = False
            for attribute, format in RESPONSE_FORMATS.items():
                match = re.match(attribute, rawInput)
                if match:
                    match_found = True
                    _LOGGER.debug(f'REGEX MATCH: {attribute} -> {format["name"]}')
                    result['attribute'] = format['attr']
                    result['name'] = format['name']
                    result['status'] = format['status']
                    result['handler'] = "handle_%s" % format['handler']
                    result['callback'] = "callback_%s" % format['handler']
                    
                    if format['handler'] == 'area_state_change':
                        result['area'] = format['area']
                        
                    if match.groups():
                        result['data'] = match.group('data')
                    else:
                        result['data'] = ''
                    break
            
            if not match_found:
                _LOGGER.debug(f'NO REGEX MATCH found for line: {rawInput}')
                
        return result

    async def keep_alive(self):
        """Smart keepalive: polls STATUS only when idle, with watchdog timeout check."""
        _LOGGER.info(f"Smart keep-alive started (interval: {self._alarmPanel.keepalive_interval}s, watchdog: {self._watchdog_timeout}s)")
        check_interval = min(5.0, max(0.1, self._alarmPanel.keepalive_interval / 2))

        while not self._shutdown:
            await asyncio.sleep(check_interval)
            if self._shutdown or not self._connected:
                continue

            now = time.monotonic()
            time_since_rx = now - self._last_rx_time

            # 1. Watchdog: check if ping was sent and no response was received within watchdog timeout
            if self._last_keepalive_sent > 0:
                time_since_ping = now - self._last_keepalive_sent
                if time_since_ping > self._watchdog_timeout and time_since_rx > self._watchdog_timeout:
                    _LOGGER.warning(
                        f"WATCHDOG TIMEOUT: No response from Crow IP Module for {int(time_since_rx)}s "
                        f"(keepalive STATUS sent {int(time_since_ping)}s ago). Hardware may be frozen. "
                        f"Dropping stale socket and reconnecting..."
                    )
                    self._last_keepalive_sent = 0.0
                    self.disconnect()
                    self._connected = False
                    self._alarmPanel._loginTimeoutCallback(False)
                    ensure_future(self.reconnect(self._alarmPanel.connection_timeout), loop=self._eventLoop)
                    continue

            # 2. Smart keep-alive: only send STATUS if no traffic was received within keepalive_interval
            if time_since_rx >= self._alarmPanel.keepalive_interval:
                _LOGGER.debug(f"No traffic received for {int(time_since_rx)}s. Sending Keepalive (STATUS)...")
                self._last_keepalive_sent = now
                self.send_command('status', '')

    def arm_stay(self):
        self.send_command('stay', '')

    def arm_away(self):
        self.send_command('arm', '')

    def disarm(self, code):
        self._cachedCode = code
        self.send_command('disarm', str(code)+'E')

    def send_keys(self, keys):
        self.send_command('keys', str(keys)+'E')    

    def panic_alarm(self, panicType):
        self.send_command('panic', '')

    def toggle_output(self, outputNumber):
        self.send_command('toogle_output_x', str(outputNumber))	

    def handle_connect_failure(self):
        """Handler for if we fail to connect to the Module."""
        _LOGGER.warning(f"Connection failure to Crow IP Module at {self._alarmPanel.host}:{self._alarmPanel.port}.")
        self._connected = False
        self._last_keepalive_sent = 0.0
        if not self._shutdown:
            _LOGGER.info(f"Scheduling reconnect in {self._alarmPanel.connection_timeout}s...")
            self._alarmPanel._loginTimeoutCallback(False)
            ensure_future(self.reconnect(self._alarmPanel.connection_timeout), loop=self._eventLoop)

    def activate_relay(self, relayNo):
        if relayNo == 1:
            self.send_command('relay_1_on', '')
        else:
            self.send_command('relay_2_on', '')
		
    def handle_system_state_change(self, msg):
        _LOGGER.debug(f"Handle System State: {msg['name']} -> {msg['status']}")
        self._alarmPanel.system_state['status'][msg['attribute']] = msg['status']
        return msg['attribute']

    def handle_output_state_change(self, msg):
        _LOGGER.debug(f"Handle Output State: {msg['name']} (Output {msg['data']}) -> {msg['status']}")
        outputNumber = msg['data']
        self._alarmPanel.output_state[int(msg['data'])]['status'][msg['attribute']] = msg['status']
        return outputNumber

    def handle_area_state_change(self, msg):
        _LOGGER.debug(f"Handle Area State: {msg['name']} (Area {msg['area']}) -> {msg['status']}")
        if msg['area'] == '1':
            areaNumber = 'A'
        else:
            areaNumber = 'B'
        
        area_idx = int(msg['area'])
        
        # Reset Area Status flags before setting the new one? 
        # CAREFUL: Logic from original lib kept here, but logging added
        self._alarmPanel.area_state[area_idx]['status']['armed'] = False
        self._alarmPanel.area_state[area_idx]['status']['stay_armed'] = False
        self._alarmPanel.area_state[area_idx]['status']['disarmed'] = False
        self._alarmPanel.area_state[area_idx]['status']['exit_delay'] = False
        self._alarmPanel.area_state[area_idx]['status']['stay_exit_delay'] = False
        
        self._alarmPanel.area_state[area_idx]['status'][msg['attribute']] = msg['status']
        
        if self._alarmPanel.area_state[area_idx]['status']['disarmed']:
            self._alarmPanel.area_state[area_idx]['status']['alarm'] = False
            self._alarmPanel.area_state[area_idx]['status']['alarm_zone'] = ''

        return areaNumber
 
    def handle_zone_state_change(self, msg):
        _LOGGER.debug(f"Handle Zone State: {msg['name']} (Zone {msg['data']})")
        zoneNumber = msg['data']
        self._alarmPanel.zone_state[int(zoneNumber)]['status'][msg['attribute']] = msg['status']
        
        if msg['attribute'] == 'alarm':
            if msg['status']:
                _LOGGER.warning(f'ALARM RAISED on Zone {zoneNumber}!!!')                
                self._alarmPanel.area_state[1]['status']['alarm_zone'] = zoneNumber
                self._alarmPanel.area_state[2]['status']['alarm_zone'] = zoneNumber
                self._alarmPanel.area_state[1]['status']['alarm'] = True
                self._alarmPanel.area_state[2]['status']['alarm'] = True
            else:
                _LOGGER.info(f'ALARM RESTORED on Zone {zoneNumber}...') 
                self._alarmPanel.area_state[1]['status']['alarm_zone'] = ''
                self._alarmPanel.area_state[2]['status']['alarm_zone'] = ''
                self._alarmPanel.area_state[1]['status']['alarm'] = False
                self._alarmPanel.area_state[2]['status']['alarm'] = False
            
            # Trigger Area updates because Alarm state implies Area state change
            try:
                _LOGGER.debug('Triggering Area State Callbacks due to Zone Alarm change...')                
                self._alarmPanel.callback_area_state_change('A')
                self._alarmPanel.callback_area_state_change('B')
            except (AttributeError, TypeError, KeyError) as err:
                _LOGGER.debug(f"Error triggering area callback from zone: {err}")

        return zoneNumber