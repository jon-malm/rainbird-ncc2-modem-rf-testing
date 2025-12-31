"""
SCPI Connection Module

Low-level SCPI communication over TCP/IP for R&S instruments.
Implements the SCPI-RAW protocol used by CMW500 on port 5025.
"""

import socket
import time
import logging
from typing import Optional, List, Union
from dataclasses import dataclass
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_PORT = 5025  # Standard SCPI-RAW port for R&S instruments
DEFAULT_TIMEOUT = 10.0  # seconds
DEFAULT_READ_TERMINATOR = b"\n"
DEFAULT_WRITE_TERMINATOR = "\n"
CHUNK_SIZE = 4096


@dataclass
class SCPIResponse:
    """Container for SCPI query responses."""
    raw: str
    success: bool
    error_code: Optional[int] = None
    error_message: Optional[str] = None

    @property
    def value(self) -> str:
        """Return the response value, stripped of whitespace."""
        return self.raw.strip()

    def as_float(self) -> float:
        """Parse response as float."""
        return float(self.value)

    def as_int(self) -> int:
        """Parse response as integer."""
        return int(float(self.value))

    def as_bool(self) -> bool:
        """Parse response as boolean (ON/OFF, 1/0, TRUE/FALSE)."""
        val = self.value.upper()
        return val in ("ON", "1", "TRUE", "YES")

    def as_list(self, separator: str = ",") -> List[str]:
        """Parse response as list."""
        return [item.strip() for item in self.value.split(separator)]


class SCPIError(Exception):
    """Base exception for SCPI communication errors."""
    pass


class SCPIConnectionError(SCPIError):
    """Connection-related errors."""
    pass


class SCPITimeoutError(SCPIError):
    """Timeout errors."""
    pass


class SCPICommandError(SCPIError):
    """Command execution errors."""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"SCPI Error {code}: {message}")


class SCPIConnection:
    """
    Low-level SCPI connection to R&S CMW500 or similar instruments.

    Provides basic SCPI command/query functionality using TCP sockets.
    Supports the SCPI-RAW protocol on the default port 5025.

    Example:
        >>> conn = SCPIConnection("192.168.1.100")
        >>> conn.connect()
        >>> idn = conn.query("*IDN?")
        >>> print(idn.value)
        Rohde&Schwarz,CMW500,1234567890,3.8.10
        >>> conn.disconnect()
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        auto_connect: bool = False
    ):
        """
        Initialize SCPI connection parameters.

        Args:
            host: IP address or hostname of the instrument
            port: SCPI port (default 5025)
            timeout: Socket timeout in seconds
            auto_connect: If True, connect immediately
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._connected = False

        if auto_connect:
            self.connect()

    @property
    def connected(self) -> bool:
        """Check if connection is active."""
        return self._connected and self._socket is not None

    def connect(self) -> None:
        """
        Establish connection to the instrument.

        Raises:
            SCPIConnectionError: If connection fails
        """
        if self._connected:
            return

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            self._connected = True
            logger.info(f"Connected to {self.host}:{self.port}")
        except socket.timeout as e:
            raise SCPITimeoutError(
                f"Connection to {self.host}:{self.port} timed out"
            ) from e
        except socket.error as e:
            raise SCPIConnectionError(
                f"Failed to connect to {self.host}:{self.port}: {e}"
            ) from e

    def disconnect(self) -> None:
        """Close the connection."""
        if self._socket:
            try:
                self._socket.close()
            except socket.error:
                pass
            finally:
                self._socket = None
                self._connected = False
                logger.info(f"Disconnected from {self.host}:{self.port}")

    def __enter__(self) -> "SCPIConnection":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()

    def write(self, command: str) -> None:
        """
        Send a SCPI command without waiting for response.

        Args:
            command: SCPI command string

        Raises:
            SCPIConnectionError: If not connected or send fails
        """
        if not self.connected:
            raise SCPIConnectionError("Not connected to instrument")

        # Ensure command ends with terminator
        if not command.endswith(DEFAULT_WRITE_TERMINATOR):
            command += DEFAULT_WRITE_TERMINATOR

        try:
            self._socket.sendall(command.encode("ascii"))
            logger.debug(f"Sent: {command.strip()}")
        except socket.error as e:
            self._connected = False
            raise SCPIConnectionError(f"Failed to send command: {e}") from e

    def read(self) -> str:
        """
        Read response from the instrument.

        Returns:
            Response string

        Raises:
            SCPITimeoutError: If read times out
            SCPIConnectionError: If connection error occurs
        """
        if not self.connected:
            raise SCPIConnectionError("Not connected to instrument")

        try:
            response = b""
            while True:
                chunk = self._socket.recv(CHUNK_SIZE)
                if not chunk:
                    break
                response += chunk
                if DEFAULT_READ_TERMINATOR in chunk:
                    break

            decoded = response.decode("ascii").strip()
            logger.debug(f"Received: {decoded[:100]}...")
            return decoded

        except socket.timeout as e:
            raise SCPITimeoutError("Read operation timed out") from e
        except socket.error as e:
            self._connected = False
            raise SCPIConnectionError(f"Failed to read response: {e}") from e

    def query(self, command: str) -> SCPIResponse:
        """
        Send a query command and return the response.

        Args:
            command: SCPI query command (should end with ?)

        Returns:
            SCPIResponse containing the result
        """
        self.write(command)
        response = self.read()
        return SCPIResponse(raw=response, success=True)

    def write_and_verify(self, command: str, delay: float = 0.1) -> bool:
        """
        Send a command and verify it completed without errors.

        Args:
            command: SCPI command
            delay: Delay before checking for errors

        Returns:
            True if command executed successfully

        Raises:
            SCPICommandError: If command caused an error
        """
        self.write(command)
        time.sleep(delay)

        # Check for errors using SCPI error queue
        error_response = self.query("SYSTem:ERRor?")
        parts = error_response.value.split(",", 1)

        error_code = int(parts[0])
        if error_code != 0:
            error_msg = parts[1].strip('"') if len(parts) > 1 else "Unknown error"
            raise SCPICommandError(error_code, error_msg)

        return True

    def reset(self) -> None:
        """Reset instrument to default state (*RST)."""
        self.write("*RST")
        self.wait_for_completion()

    def clear_status(self) -> None:
        """Clear status registers (*CLS)."""
        self.write("*CLS")

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all pending operations to complete.

        Uses *OPC? query which blocks until operations complete.

        Args:
            timeout: Optional override for timeout

        Returns:
            True when operations complete
        """
        original_timeout = self._socket.gettimeout() if self._socket else None

        try:
            if timeout and self._socket:
                self._socket.settimeout(timeout)

            response = self.query("*OPC?")
            return response.as_bool()

        finally:
            if original_timeout is not None and self._socket:
                self._socket.settimeout(original_timeout)

    def get_identification(self) -> str:
        """Get instrument identification string (*IDN?)."""
        return self.query("*IDN?").value

    def get_options(self) -> List[str]:
        """Get installed hardware/software options (*OPT?)."""
        return self.query("*OPT?").as_list()

    def get_error_queue(self) -> List[tuple]:
        """
        Read all errors from the error queue.

        Returns:
            List of (error_code, error_message) tuples
        """
        errors = []
        while True:
            response = self.query("SYSTem:ERRor?")
            parts = response.value.split(",", 1)
            code = int(parts[0])

            if code == 0:
                break

            msg = parts[1].strip('"') if len(parts) > 1 else ""
            errors.append((code, msg))

        return errors

    def clear_error_queue(self) -> None:
        """Clear all errors from the error queue."""
        self.get_error_queue()  # Reading clears the queue


@contextmanager
def scpi_connection(
    host: str,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT
):
    """
    Context manager for SCPI connections.

    Example:
        >>> with scpi_connection("192.168.1.100") as conn:
        ...     print(conn.get_identification())
    """
    conn = SCPIConnection(host, port, timeout)
    try:
        conn.connect()
        yield conn
    finally:
        conn.disconnect()
