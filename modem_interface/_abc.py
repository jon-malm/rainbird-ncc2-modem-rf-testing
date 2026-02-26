"""Abstract base class defining the modem interface contract."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Optional

import serial

from ._types import SignalQuality


class ModemManager(ABC):
    """Abstract interface for cellular modem control.

    Defines the methods and properties that the test framework requires
    from any modem implementation.  All cellular modems communicate via
    AT commands over a serial interface, so ``serial`` and ``port`` are
    part of the base contract.

    Concrete implementations must subclass this ABC and implement every
    abstract method and property.
    """

    # --- Connection lifecycle ---

    @abstractmethod
    def find_at_port(self) -> Optional[str]:
        """Auto-detect the modem's AT command port.

        Returns:
            Port path string, or None if not found.
        """
        ...

    @abstractmethod
    def connect(self, port: str = None) -> bool:
        """Open a serial connection to the modem.

        Args:
            port: Serial port path.  Auto-detects if not provided.

        Returns:
            True if connection successful.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the serial connection."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the serial connection is open."""
        ...

    # --- AT command interface ---

    @abstractmethod
    def send_command(
        self,
        cmd: str,
        timeout: float = None,
        interrupt_check: Callable[[], bool] = None,
    ) -> str:
        """Send an AT command and return the response.

        Args:
            cmd: AT command string to send.
            timeout: Response timeout in seconds.
            interrupt_check: Optional callback that returns True to abort.

        Returns:
            Complete response string including result code.
        """
        ...

    # --- Modem information ---

    @abstractmethod
    def get_modem_info(self) -> dict:
        """Get basic modem information.

        Returns:
            Dictionary with keys: manufacturer, model, firmware, imei.
        """
        ...

    @abstractmethod
    def get_sim_status(self) -> str:
        """Get SIM card status string (e.g. 'READY')."""
        ...

    # --- Network status ---

    @abstractmethod
    def get_signal_quality(self) -> SignalQuality:
        """Get current signal quality measurements.

        Returns:
            SignalQuality instance with mode-specific measurements.
        """
        ...

    @abstractmethod
    def is_registered(self) -> bool:
        """Check if modem is registered on a network."""
        ...

    # --- Serial interface ---

    @property
    @abstractmethod
    def port(self) -> Optional[str]:
        """The serial port path (e.g. '/dev/ttyUSB2')."""
        ...

    @property
    @abstractmethod
    def serial(self) -> Optional[serial.Serial]:
        """The underlying pyserial connection object."""
        ...
