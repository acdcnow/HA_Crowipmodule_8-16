import logging
import socket
import threading
import time

_LOGGER = logging.getLogger(__name__)

class CrowBaseClient:
    """Thread-safe base client for Crow IP Module with reconnect guard."""

    def __init__(self, host: str, port: int = 5002, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

        self._socket = None
        self._lock = threading.Lock()
        self._is_connecting = False
        self._is_connected = False

        self._reconnect_timer = None
        self._reconnect_delay = 10  # Initial delay in seconds
        self._max_reconnect_delay = 60  # Maximum backoff cap

        self.callback_connected = None
        self.callback_disconnected = None

    def connect(self) -> bool:
        """Establish a connection to the Crow IP Module safely."""
        with self._lock:
            if self._is_connecting or self._is_connected:
                _LOGGER.debug(
                    "Connection attempt skipped: Connection already active or in progress."
                )
                return False
            self._is_connecting = True

        # Stop any pending reconnect timers before attempting a new connection
        self._cancel_reconnect_timer()

        try:
            _LOGGER.info("Starting connection to Crow IP Module at %s:%s", self.host, self.port)

            # Cleanup old socket state before re-opening
            self._close_socket()
            time.sleep(0.5)  # Brief pause to let hardware port release

            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))

            self._is_connected = True
            self._reconnect_delay = 10  # Reset backoff on success

            _LOGGER.info(
                "Connection successfully made to Crow IP Module at %s:%s!",
                self.host,
                self.port,
            )

            if callable(self.callback_connected):
                _LOGGER.debug("Invoking callback_connected(True)")
                self.callback_connected(True)

            return True

        except (socket.timeout, socket.error, Exception) as err:
            _LOGGER.warning(
                "Timeout or error connecting to Crow IP module (%s:%s): %s",
                self.host,
                self.port,
                err,
            )
            _LOGGER.warning("Connection failure to Crow IP Module at %s:%s.", self.host, self.port)
            
            self._is_connected = False
            self.schedule_reconnect()
            return False

        finally:
            with self._lock:
                self._is_connecting = False

    def schedule_reconnect(self):
        """Schedule a reconnection attempt using exponential backoff."""
        with self._lock:
            self._cancel_reconnect_timer()

            delay = self._reconnect_delay
            # Increase delay exponentially for subsequent failures (e.g. 10s -> 20s -> 40s -> 60s)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

            _LOGGER.info("Scheduling reconnect to Crow IP Module in %d seconds...", delay)

            self._reconnect_timer = threading.Timer(delay, self._trigger_reconnect)
            self._reconnect_timer.daemon = True
            self._reconnect_timer.start()

    def _trigger_reconnect(self):
        """Timer execution target to reconnect."""
        _LOGGER.info("Reconnecting to Crow IP Module now...")
        self.disconnect(reconnecting=True)
        self.connect()

    def _cancel_reconnect_timer(self):
        """Cancel any existing pending reconnect timer."""
        if self._reconnect_timer is not None:
            _LOGGER.debug("Canceling active reconnect timer.")
            self._reconnect_timer.cancel()
            self._reconnect_timer = None

    def disconnect(self, reconnecting: bool = False):
        """Disconnect and reset state cleanly."""
        with self._lock:
            if not reconnecting:
                self._cancel_reconnect_timer()

            self._is_connected = False
            _LOGGER.debug("Disconnecting transport...")
            self._close_socket()
            _LOGGER.info("Connection to Crow IP Module closed cleanly.")

            if callable(self.callback_disconnected) and not reconnecting:
                self.callback_disconnected()

    def _close_socket(self):
        """Internal method to close raw socket."""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            finally:
                self._socket.close()
                self._socket = None

    @property
    def is_connected(self) -> bool:
        """Return current connection status."""
        return self._is_connected
