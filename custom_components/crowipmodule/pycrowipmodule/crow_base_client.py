import logging
import socket
import threading
import time

_LOGGER = logging.getLogger(__name__)


class CrowIPModuleClient:
    """Thread-safe client for Crow IP Module with background worker loop and reconnect guards."""

    def __init__(self, *args, **kwargs):
        self.panel = None
        self.host = None
        self.port = None
        self.timeout = 5.0
        self.keepalive = 60.0

        # Parse positional arguments: (panel, host, port) vs (host, port)
        if args:
            if not isinstance(args[0], str):
                self.panel = args[0]
                if len(args) > 1 and args[1] is not None:
                    self.host = str(args[1])
                if len(args) > 2 and args[2] is not None:
                    self.port = int(args[2])
            else:
                self.host = str(args[0])
                if len(args) > 1 and args[1] is not None:
                    self.port = int(args[1])

        # Parse keyword arguments
        if "panel" in kwargs and kwargs["panel"] is not None:
            self.panel = kwargs["panel"]
        if "host" in kwargs and kwargs["host"] is not None:
            self.host = str(kwargs["host"])
        elif "ip" in kwargs and kwargs["ip"] is not None:
            self.host = str(kwargs["ip"])
        if "port" in kwargs and kwargs["port"] is not None:
            self.port = int(kwargs["port"])
        if "timeout" in kwargs and kwargs["timeout"] is not None:
            self.timeout = float(kwargs["timeout"])
        if "keepalive" in kwargs and kwargs["keepalive"] is not None:
            self.keepalive = float(kwargs["keepalive"])

        # Extract host and port directly from parent panel attributes if not explicitly passed
        if self.panel:
            if not self.host:
                for attr in ("_host", "host", "_ip", "ip", "_address", "address"):
                    if hasattr(self.panel, attr) and getattr(self.panel, attr):
                        self.host = str(getattr(self.panel, attr))
                        break
            if not self.port:
                for attr in ("_port", "port"):
                    if hasattr(self.panel, attr) and getattr(self.panel, attr):
                        self.port = int(getattr(self.panel, attr))
                        break

        # Fallbacks if still unspecified
        if not self.host:
            self.host = "127.0.0.1"
        if not self.port:
            self.port = 5002

        self._socket = None
        self._lock = threading.Lock()
        self._connect_lock = threading.Lock()

        self._is_connecting = False
        self._is_connected = False
        self._running = False
        self._thread = None

        self._reconnect_timer = None
        self._reconnect_delay = 10
        self._max_reconnect_delay = 60

        # Callbacks expected by pycrowipmodule.alarm_panel
        self.callback_connected = None
        self.callback_disconnected = None
        self.callback_data = None

    def start(self):
        """Start the background worker thread."""
        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                _LOGGER.debug("Client worker thread is already running.")
                return

            self._running = True
            self._thread = threading.Thread(target=self._run_loop, name="CrowIPClientThread", daemon=True)
            self._thread.start()

    def stop(self):
        """Stop the background worker thread and disconnect cleanly."""
        self._running = False
        self.disconnect()

    def _run_loop(self):
        """Main thread loop for connection handling and TCP stream processing."""
        if self.connect():
            time.sleep(0.2)
            self.request_status()

            # Follow-up status request at +4s to ensure HA entities receive state after setup completes
            sync_timer = threading.Timer(4.0, self.request_status)
            sync_timer.daemon = True
            sync_timer.start()

            self._listen_loop()

    def connect(self) -> bool:
        """Establish connection safely using a single-execution guard lock."""
        with self._connect_lock:
            if self._is_connecting:
                _LOGGER.debug("Connection attempt skipped: Already in progress.")
                return False
            if self._is_connected:
                _LOGGER.debug("Connection attempt skipped: Already connected.")
                return True
            self._is_connecting = True

        self._cancel_reconnect_timer()

        try:
            _LOGGER.info("Connecting to Crow IP Module on host: %s, port: %s", self.host, self.port)

            self._close_socket()
            time.sleep(0.5)

            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))

            self._is_connected = True
            self._reconnect_delay = 10

            _LOGGER.info("Connection successfully made to Crow IP Module at %s:%s!", self.host, self.port)

            if callable(self.callback_connected):
                try:
                    self.callback_connected(True)
                except Exception as cb_err:
                    _LOGGER.error("Error executing callback_connected: %s", cb_err)

            return True

        except (socket.timeout, socket.error, Exception) as err:
            _LOGGER.warning("Timeout or error connecting to Crow IP module (%s:%s): %s", self.host, self.port, err)
            self._is_connected = False
            self._close_socket()

            if callable(self.callback_connected):
                try:
                    self.callback_connected(False)
                except Exception:
                    pass

            self.schedule_reconnect()
            return False

        finally:
            with self._connect_lock:
                self._is_connecting = False

    def _listen_loop(self):
        """Continuously read data from the TCP socket while connected."""
        buffer = ""
        while self._running and self._is_connected and self._socket:
            try:
                data = self._socket.recv(1024)
                if not data:
                    _LOGGER.warning("Crow IP Module connection closed by remote host.")
                    break

                buffer += data.decode("ascii", errors="ignore")
                while "\r\n" in buffer or "\n" in buffer:
                    if "\r\n" in buffer:
                        line, buffer = buffer.split("\r\n", 1)
                    else:
                        line, buffer = buffer.split("\n", 1)

                    clean_line = line.strip()
                    if clean_line:
                        _LOGGER.debug("RX RAW: %s", clean_line)
                        self._dispatch_line(clean_line)

            except socket.timeout:
                continue
            except (socket.error, OSError) as err:
                if not self._running or not self._is_connected:
                    _LOGGER.debug("Socket connection closed during teardown.")
                else:
                    _LOGGER.warning("Error reading from socket: %s", err)
                break
            except Exception as err:
                _LOGGER.warning("Unexpected error reading from socket: %s", err)
                break

        self.disconnect(reconnecting=True)
        if self._running:
            self.schedule_reconnect()

    def _dispatch_line(self, line: str):
        """Route received line to panel parser methods and notify all registered HA subscribers."""
        if not self.panel:
            return

        # 1. Execute panel parser method so internal area and zone dictionaries update
        parser_methods = (
            "_commandResponseCallback",
            "commandResponseCallback",
            "handle_line",
            "_handle_line",
            "process_line",
            "_process_line",
            "parse_line",
            "_parse_line",
            "handle_data",
            "_handle_data",
        )
        for method_name in parser_methods:
            if hasattr(self.panel, method_name):
                method = getattr(self.panel, method_name)
                if callable(method):
                    try:
                        method(line)
                        break
                    except Exception as err:
                        _LOGGER.error("Error executing panel parser %s: %s", method_name, err)

        # 2. Collect all registered subscriber callbacks across self.panel and self
        callbacks_to_trigger = []

        # Check list/set containers where HA entity listeners are registered
        for container_attr in (
            "_callbacks", "callbacks",
            "_listeners", "listeners",
            "_subscribers", "subscribers",
            "_handlers", "handlers"
        ):
            container = getattr(self.panel, container_attr, None)
            if isinstance(container, (list, tuple, set)):
                for item in container:
                    if callable(item) and item not in callbacks_to_trigger:
                        callbacks_to_trigger.append(item)

        # Check single callback properties
        for obj in (self.panel, self):
            for cb_attr in ("callback", "_callback", "callback_data", "_callback_data", "data_callback"):
                cb = getattr(obj, cb_attr, None)
                if callable(cb):
                    cb_name = getattr(cb, "__name__", "")
                    if cb_name != "DefaultCallback" and cb not in callbacks_to_trigger:
                        callbacks_to_trigger.append(cb)

        # 3. Execute each discovered Home Assistant subscriber to trigger state write
        for cb in callbacks_to_trigger:
            try:
                try:
                    cb(line)
                except TypeError:
                    cb()
            except Exception as cb_err:
                _LOGGER.error("Error executing HA subscriber callback %s: %s", cb, cb_err)

    def request_status(self) -> bool:
        """Request initial status dump from panel."""
        _LOGGER.info("Requesting initial STATUS dump from panel...")
        return self.send_command("STATUS", "")

    def send_command(self, code: str, data: str = "") -> bool:
        """Send a raw text command to the panel."""
        if not self._is_connected or not self._socket:
            _LOGGER.warning("Cannot send command '%s': Not connected to Crow IP Module.", code)
            return False

        try:
            cmd_str = f"{code} {data}\r\n" if data else f"{code}\r\n"
            _LOGGER.debug("Preparing command: Code=%s, Data=%s", code, data)
            _LOGGER.debug("TX RAW: %s", cmd_str.encode("ascii"))

            with self._lock:
                self._socket.sendall(cmd_str.encode("ascii"))
            return True
        except Exception as err:
            _LOGGER.error("Failed to send command '%s' to panel: %s", code, err)
            self.disconnect(reconnecting=True)
            self.schedule_reconnect()
            return False

    def schedule_reconnect(self, delay: int = None):
        """Schedule a single reconnection attempt with exponential backoff."""
        with self._connect_lock:
            self._cancel_reconnect_timer()

            if delay is None:
                delay = self._reconnect_delay
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

            _LOGGER.info("Scheduling reconnect to Crow IP Module in %d seconds...", delay)

            self._reconnect_timer = threading.Timer(delay, self._trigger_reconnect)
            self._reconnect_timer.daemon = True
            self._reconnect_timer.start()

    def _trigger_reconnect(self):
        """Timer callback to attempt reconnection in a background thread."""
        _LOGGER.info("Reconnecting to Crow IP Module now...")
        self.disconnect(reconnecting=True)
        with self._lock:
            self._running = False
        self.start()

    def _cancel_reconnect_timer(self):
        """Cancel active reconnect timers."""
        if self._reconnect_timer is not None:
            _LOGGER.debug("Canceling active reconnect timer.")
            try:
                self._reconnect_timer.cancel()
            except Exception:
                pass
            self._reconnect_timer = None

    def disconnect(self, reconnecting: bool = False):
        """Cleanly close socket transport and reset state."""
        with self._connect_lock:
            if not reconnecting:
                self._cancel_reconnect_timer()

            self._is_connected = False
            _LOGGER.debug("Disconnecting transport...")
            self._close_socket()
            _LOGGER.info("Connection to Crow IP Module closed cleanly.")

            if callable(self.callback_disconnected) and not reconnecting:
                try:
                    self.callback_disconnected()
                except Exception as err:
                    _LOGGER.error("Error executing callback_disconnected: %s", err)

    def _close_socket(self):
        """Safely close active socket connection."""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    @property
    def is_connected(self) -> bool:
        """Return current connection state."""
        return self._is_connected
