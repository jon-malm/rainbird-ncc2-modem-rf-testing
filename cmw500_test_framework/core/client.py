"""
CMW500 Client Module

High-level client for controlling the R&S CMW500 Wideband Radio Communication Tester.
Provides an abstraction over raw SCPI commands for common operations.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

from .scpi import SCPIConnection, SCPIResponse, SCPIError, SCPICommandError
from .config import Config, InstrumentConfig

logger = logging.getLogger(__name__)


class CellState(Enum):
    """Cell state enumeration."""
    OFF = "OFF"
    ON = "ON"
    ADJUSTING = "ADJ"


class SignalingState(Enum):
    """Signaling connection state."""
    IDLE = "IDLE"
    CONNECTING = "CON"
    CONNECTED = "ATT"
    REGISTERED = "REG"
    CEST = "CEST"  # Connection established


class DuplexMode(Enum):
    """Duplex mode enumeration."""
    FDD = "FDD"
    TDD = "TDD"


@dataclass
class SystemInfo:
    """CMW500 system information."""
    manufacturer: str
    model: str
    serial_number: str
    firmware_version: str
    options: List[str]


@dataclass
class MeasurementResult:
    """Container for measurement results."""
    name: str
    value: float
    unit: str
    reliability: str = "OK"
    timestamp: Optional[float] = None

    def __str__(self) -> str:
        return f"{self.name}: {self.value} {self.unit} ({self.reliability})"


class CMW500Client:
    """
    High-level client for CMW500 control.

    Provides methods for:
    - System control and configuration
    - LTE signaling and measurements
    - General purpose RF generation/analysis
    - Network simulation
    - Fading channel control

    Example:
        >>> client = CMW500Client("192.168.1.100")
        >>> client.connect()
        >>> print(client.get_system_info())
        >>> client.lte.configure_cell(band=1, bandwidth=10)
        >>> client.lte.cell_on()
        >>> client.disconnect()
    """

    def __init__(
        self,
        host: str = None,
        port: int = 5025,
        timeout: float = 10.0,
        config: Config = None
    ):
        """
        Initialize CMW500 client.

        Args:
            host: IP address or hostname (overrides config)
            port: SCPI port (overrides config)
            timeout: Connection timeout (overrides config)
            config: Configuration object (optional)
        """
        self._config = config

        # Use config values as defaults, allow parameter overrides
        if config:
            self._host = host or config.instrument.host
            self._port = port if port != 5025 else config.instrument.port
            self._timeout = timeout if timeout != 10.0 else config.instrument.timeout
        else:
            self._host = host or "localhost"
            self._port = port
            self._timeout = timeout

        self._scpi: Optional[SCPIConnection] = None
        self._system_info: Optional[SystemInfo] = None

        # Sub-modules (lazy initialization)
        self._lte = None
        self._gprf = None
        self._system = None

    @property
    def connected(self) -> bool:
        """Check if connected to instrument."""
        return self._scpi is not None and self._scpi.connected

    @property
    def scpi(self) -> SCPIConnection:
        """Get the underlying SCPI connection."""
        if not self._scpi:
            raise SCPIError("Not connected to instrument")
        return self._scpi

    @property
    def config(self) -> Optional[Config]:
        """Get the configuration object."""
        return self._config

    def connect(self) -> None:
        """
        Connect to the CMW500.

        Raises:
            SCPIConnectionError: If connection fails
        """
        if self.connected:
            logger.warning("Already connected")
            return

        self._scpi = SCPIConnection(
            host=self._host,
            port=self._port,
            timeout=self._timeout
        )
        self._scpi.connect()

        # Clear any pending errors
        self._scpi.clear_status()
        self._scpi.clear_error_queue()

        # Cache system info
        self._system_info = self._query_system_info()
        logger.info(f"Connected to {self._system_info.model} "
                   f"(S/N: {self._system_info.serial_number})")

    def disconnect(self) -> None:
        """Disconnect from the CMW500."""
        if self._scpi:
            self._scpi.disconnect()
            self._scpi = None
            self._system_info = None

    def __enter__(self) -> "CMW500Client":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()

    def _query_system_info(self) -> SystemInfo:
        """Query and parse system identification."""
        idn = self._scpi.query("*IDN?").value
        parts = idn.split(",")

        options = []
        try:
            options = self._scpi.query("*OPT?").as_list()
        except SCPIError:
            pass

        return SystemInfo(
            manufacturer=parts[0] if len(parts) > 0 else "Unknown",
            model=parts[1] if len(parts) > 1 else "Unknown",
            serial_number=parts[2] if len(parts) > 2 else "Unknown",
            firmware_version=parts[3] if len(parts) > 3 else "Unknown",
            options=options,
        )

    def get_system_info(self) -> SystemInfo:
        """
        Get cached system information.

        Returns:
            SystemInfo dataclass with instrument details
        """
        if not self._system_info:
            if not self.connected:
                raise SCPIError("Not connected to instrument")
            self._system_info = self._query_system_info()
        return self._system_info

    def get_identification(self) -> str:
        """Get instrument identification string."""
        return self._scpi.get_identification()

    def reset(self) -> None:
        """Reset instrument to default state."""
        logger.info("Resetting instrument...")
        self._scpi.reset()
        time.sleep(2)  # Allow time for reset

    def preset(self) -> None:
        """Preset instrument (SYSTem:PRESet)."""
        logger.info("Presetting instrument...")
        self._scpi.write("SYSTem:PRESet")
        self._scpi.wait_for_completion(timeout=30)

    # =========================================================================
    # System Control
    # =========================================================================

    def get_system_date_time(self) -> str:
        """Get system date and time."""
        date = self._scpi.query("SYSTem:DATE?").value
        time_val = self._scpi.query("SYSTem:TIME?").value
        return f"{date} {time_val}"

    def set_display_update(self, enabled: bool) -> None:
        """
        Enable/disable display updates during remote control.

        Disabling can improve measurement speed.
        """
        state = "ON" if enabled else "OFF"
        self._scpi.write(f"SYSTem:DISPlay:UPDate {state}")

    def get_temperature(self) -> float:
        """Get instrument internal temperature in Celsius."""
        return self._scpi.query("SYSTem:TEMPerature?").as_float()

    def screenshot(self, filename: str) -> None:
        """
        Save a screenshot to the instrument's filesystem.

        Args:
            filename: Output filename (on instrument)
        """
        self._scpi.write(f'HCOPy:DESTination "{filename}"')
        self._scpi.write("HCOPy:IMMediate")
        self._scpi.wait_for_completion()

    # =========================================================================
    # RF Port Configuration
    # =========================================================================

    def get_rf_ports(self) -> List[str]:
        """Get list of available RF ports."""
        # Common CMW500 RF ports
        return ["RF1COM", "RF2COM", "RF3", "RF4"]

    def set_external_attenuation(
        self,
        port: str,
        attenuation_db: float,
        direction: str = "BOTH"
    ) -> None:
        """
        Set external attenuation for an RF port.

        Args:
            port: RF port name (e.g., "RF1COM")
            attenuation_db: Attenuation in dB
            direction: "INPUT", "OUTPUT", or "BOTH"
        """
        if direction.upper() in ("INPUT", "BOTH"):
            self._scpi.write(
                f"CONFigure:BASE:FDCorrection:CTABle:EATTenuation:INPut "
                f"{port},{attenuation_db}"
            )
        if direction.upper() in ("OUTPUT", "BOTH"):
            self._scpi.write(
                f"CONFigure:BASE:FDCorrection:CTABle:EATTenuation:OUTPut "
                f"{port},{attenuation_db}"
            )

    # =========================================================================
    # Routing Configuration
    # =========================================================================

    def configure_rf_routing(
        self,
        application: str,
        rf_port: str = "RF1COM"
    ) -> None:
        """
        Configure RF signal routing for an application.

        Args:
            application: Application name (e.g., "LTE", "GPRF")
            rf_port: Target RF port
        """
        # Route command varies by application
        self._scpi.write(f"ROUTe:{application}:SIGN:SCENario:SCELl {rf_port}")

    # =========================================================================
    # LTE Sub-module Access
    # =========================================================================

    @property
    def lte(self) -> "LTESignaling":
        """Access LTE signaling sub-module."""
        if self._lte is None:
            from ..applications.lte import LTESignaling
            self._lte = LTESignaling(self)
        return self._lte

    # =========================================================================
    # General Purpose RF Access
    # =========================================================================

    @property
    def gprf(self) -> "GeneralPurposeRF":
        """Access General Purpose RF sub-module."""
        if self._gprf is None:
            from ..applications.gprf import GeneralPurposeRF
            self._gprf = GeneralPurposeRF(self)
        return self._gprf

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def wait(self, seconds: float) -> None:
        """Wait for specified time."""
        time.sleep(seconds)

    def wait_for_completion(self, timeout: float = None) -> None:
        """Wait for pending operations to complete."""
        self._scpi.wait_for_completion(timeout)

    def check_errors(self) -> List[Tuple[int, str]]:
        """
        Check for errors in the error queue.

        Returns:
            List of (error_code, error_message) tuples
        """
        return self._scpi.get_error_queue()

    def send_command(self, command: str) -> None:
        """
        Send a raw SCPI command.

        Args:
            command: SCPI command string
        """
        self._scpi.write(command)

    def query(self, command: str) -> SCPIResponse:
        """
        Send a raw SCPI query.

        Args:
            command: SCPI query string

        Returns:
            SCPIResponse object
        """
        return self._scpi.query(command)

    # =========================================================================
    # Class Methods
    # =========================================================================

    @classmethod
    def from_config(cls, config: Config) -> "CMW500Client":
        """
        Create client from configuration object.

        Args:
            config: Configuration object

        Returns:
            CMW500Client instance
        """
        return cls(config=config)

    @classmethod
    def from_config_file(cls, path: str) -> "CMW500Client":
        """
        Create client from configuration file.

        Args:
            path: Path to YAML config file

        Returns:
            CMW500Client instance
        """
        config = Config.from_file(path)
        return cls(config=config)
