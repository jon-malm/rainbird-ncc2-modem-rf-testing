"""
WCDMA/UMTS Signaling Module

Controls WCDMA (3G) signaling functionality on the CMW500, including:
- Cell configuration and control
- Connection management
- Power level settings
- Measurements (TX power, ACLR, EVM, BER, BLER)

SCPI Command Reference:
- CONFigure:WCDMa:SIGN:... - Configuration commands
- SOURce:WCDMa:SIGN:... - Source/generator commands
- READ/FETCh/MEASure:WCDMa:SIGN:... - Measurement commands
"""

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from ..core.client import CMW500Client

logger = logging.getLogger(__name__)


class WCDMABand(Enum):
    """WCDMA/UMTS frequency bands."""
    BAND_I = 1      # 2100 MHz (IMT)
    BAND_II = 2     # 1900 MHz (PCS)
    BAND_III = 3    # 1800 MHz (DCS)
    BAND_IV = 4     # 1700/2100 MHz (AWS)
    BAND_V = 5      # 850 MHz (CLR)
    BAND_VI = 6     # 800 MHz (Japan)
    BAND_VIII = 8   # 900 MHz (E-GSM)
    BAND_IX = 9     # 1700 MHz (Japan)
    BAND_X = 10     # 1700/2100 MHz (Extended AWS)
    BAND_XI = 11    # 1500 MHz (Japan)
    BAND_XIX = 19   # 800 MHz (Japan)


class WCDMACellState(Enum):
    """WCDMA cell state."""
    OFF = "OFF"
    ON = "ON"


class WCDMAConnectionState(Enum):
    """WCDMA signaling connection state."""
    OFF = "OFF"
    IDLE = "IDLE"
    ATTACHING = "ATT"
    CONNECTED = "CEST"
    REGISTERED = "REG"


class WCDMAChannelType(Enum):
    """WCDMA channel types."""
    DPCH = "DPCH"       # Dedicated Physical Channel
    HSPDSCH = "HSDPA"   # High Speed Downlink Shared Channel
    EDCH = "HSUPA"      # Enhanced Dedicated Channel


@dataclass
class WCDMACellConfig:
    """WCDMA cell configuration parameters."""
    band: int
    uarfcn_dl: int
    scrambling_code: int
    cpich_power_dbm: float
    max_ul_power_dbm: float


@dataclass
class WCDMATxPowerResult:
    """WCDMA TX power measurement results."""
    reliability: str
    dpcch_power_dbm: float
    dpdch_power_dbm: float
    total_power_dbm: float


@dataclass
class WCDMABerResult:
    """WCDMA BER/BLER measurement results."""
    reliability: str
    ber: float
    bler: float
    num_bits: int
    num_blocks: int


class WCDMASignaling:
    """
    WCDMA/UMTS Signaling control for CMW500.

    Provides high-level methods for:
    - Cell configuration (band, UARFCN, scrambling code, power levels)
    - Cell state control (on/off)
    - Connection establishment
    - Downlink/uplink power control
    - Measurements (TX power, ACLR, EVM, BER, BLER)

    Example:
        >>> client = CMW500Client("192.168.1.100")
        >>> client.connect()
        >>>
        >>> # Configure and enable cell
        >>> client.wcdma.configure_cell(band=1, uarfcn_dl=10700)
        >>> client.wcdma.set_dl_power(cpich_power_dbm=-60)
        >>> client.wcdma.cell_on()
        >>>
        >>> # Wait for UE to attach
        >>> client.wcdma.wait_for_attach(timeout=60)
        >>>
        >>> # Perform measurements
        >>> tx_power = client.wcdma.measure_tx_power()
        >>> print(f"Total UL Power: {tx_power.total_power_dbm} dBm")
    """

    # SCPI subsystem prefixes
    CONF_PREFIX = "CONFigure:WCDMa:SIGN"
    SOURCE_PREFIX = "SOURce:WCDMa:SIGN"
    MEAS_PREFIX = "MEASure:WCDMa:SIGN"
    FETCH_PREFIX = "FETCh:WCDMa:SIGN"
    READ_PREFIX = "READ:WCDMa:SIGN"

    def __init__(self, client: "CMW500Client"):
        """
        Initialize WCDMA signaling module.

        Args:
            client: CMW500Client instance
        """
        self._client = client

    @property
    def scpi(self):
        """Get SCPI connection."""
        return self._client.scpi

    # =========================================================================
    # Cell Configuration
    # =========================================================================

    def configure_cell(
        self,
        band: int = 1,
        uarfcn_dl: int = 10700,
        scrambling_code: int = 0,
        cpich_power_dbm: float = -60.0,
    ) -> None:
        """
        Configure basic WCDMA cell parameters.

        Args:
            band: WCDMA band number (1, 2, 3, 4, 5, 6, 8, etc.)
            uarfcn_dl: Downlink UARFCN
            scrambling_code: Primary scrambling code (0-511)
            cpich_power_dbm: CPICH power in dBm
        """
        logger.info(f"Configuring WCDMA cell: Band {band}, UARFCN {uarfcn_dl}")

        # Set band
        self.scpi.write(f"{self.CONF_PREFIX}:BAND OB{band}")

        # Set UARFCN (downlink channel)
        self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:CHANnel:DL {uarfcn_dl}")

        # Set primary scrambling code
        self.scpi.write(f"{self.CONF_PREFIX}:CELL:PSCRambling {scrambling_code}")

        # Set CPICH power
        self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:DL:LEVel:CPIC {cpich_power_dbm}")

        self.scpi.wait_for_completion()

    def get_cell_config(self) -> Dict[str, any]:
        """
        Query current cell configuration.

        Returns:
            Dictionary with current cell parameters
        """
        return {
            "band": self.scpi.query(f"{self.CONF_PREFIX}:BAND?").value,
            "uarfcn_dl": self.scpi.query(f"{self.CONF_PREFIX}:RFSettings:CHANnel:DL?").value,
            "scrambling_code": self.scpi.query(f"{self.CONF_PREFIX}:CELL:PSCRambling?").value,
            "cpich_power": self.scpi.query(f"{self.CONF_PREFIX}:RFSettings:DL:LEVel:CPIC?").value,
        }

    # =========================================================================
    # Cell State Control
    # =========================================================================

    def cell_on(self) -> None:
        """Turn on the WCDMA cell."""
        logger.info("Turning WCDMA cell ON")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:STATe ON")
        self._wait_for_cell_state("ON", timeout=30)

    def cell_off(self) -> None:
        """Turn off the WCDMA cell."""
        logger.info("Turning WCDMA cell OFF")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:STATe OFF")
        self._wait_for_cell_state("OFF", timeout=10)

    def get_cell_state(self) -> str:
        """
        Get current cell state.

        Returns:
            Cell state string: "OFF", "ON", or "ADJ" (adjusting)
        """
        return self.scpi.query(f"{self.SOURCE_PREFIX}:CELL:STATe?").value

    def _wait_for_cell_state(self, target_state: str, timeout: float = 30) -> bool:
        """Wait for cell to reach target state."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            state = self.get_cell_state()
            if state == target_state:
                return True
            time.sleep(0.5)
        raise TimeoutError(f"Cell did not reach state {target_state} within {timeout}s")

    # =========================================================================
    # Power Level Control
    # =========================================================================

    def set_dl_power(
        self,
        cpich_power_dbm: float = -60.0,
        psch_power_dbm: Optional[float] = None,
        ssch_power_dbm: Optional[float] = None,
    ) -> None:
        """
        Set downlink power levels.

        Args:
            cpich_power_dbm: CPICH (pilot) power in dBm
            psch_power_dbm: Primary synchronization channel power
            ssch_power_dbm: Secondary synchronization channel power
        """
        logger.info(f"Setting DL power: CPICH = {cpich_power_dbm} dBm")

        self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:DL:LEVel:CPIC {cpich_power_dbm}")

        if psch_power_dbm is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:DL:LEVel:PSCH {psch_power_dbm}")

        if ssch_power_dbm is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:DL:LEVel:SSCH {ssch_power_dbm}")

    def set_ul_power_control(
        self,
        max_ul_power_dbm: float = 24.0,
        target_sir_db: float = 8.0,
    ) -> None:
        """
        Configure uplink power control parameters.

        Args:
            max_ul_power_dbm: Maximum UE transmit power
            target_sir_db: Target SIR for inner loop power control
        """
        self.scpi.write(f"{self.CONF_PREFIX}:UL:POWer:MAXimum {max_ul_power_dbm}")
        self.scpi.write(f"{self.CONF_PREFIX}:UL:ILPControl:TSir {target_sir_db}")

    def get_dl_power(self) -> Dict[str, float]:
        """Get current downlink power settings."""
        return {
            "cpich_power_dbm": self.scpi.query(
                f"{self.CONF_PREFIX}:RFSettings:DL:LEVel:CPIC?"
            ).as_float(),
        }

    # =========================================================================
    # Connection Management
    # =========================================================================

    def get_connection_state(self) -> str:
        """
        Get signaling connection state.

        Returns:
            Connection state string
        """
        return self.scpi.query(f"{self.SOURCE_PREFIX}:CELL:STATe:ALL?").value

    def wait_for_attach(self, timeout: float = 60) -> bool:
        """
        Wait for UE to attach to the cell.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if UE attached

        Raises:
            TimeoutError: If timeout exceeded
        """
        logger.info("Waiting for UE to attach...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            state = self.get_connection_state()
            logger.debug(f"Connection state: {state}")

            if "ATT" in state or "REG" in state or "CEST" in state:
                logger.info("UE attached successfully")
                return True

            time.sleep(1)

        raise TimeoutError(f"UE did not attach within {timeout}s")

    def wait_for_connected(self, timeout: float = 60) -> bool:
        """
        Wait for traffic channel (DCH) established.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if connected
        """
        logger.info("Waiting for DCH connected state...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            state = self.get_connection_state()
            if "CEST" in state:
                logger.info("Traffic channel established")
                return True
            time.sleep(1)

        raise TimeoutError(f"Traffic channel not established within {timeout}s")

    def disconnect_ue(self) -> None:
        """Disconnect UE from the cell."""
        logger.info("Disconnecting UE")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:RELease")
        time.sleep(1)

    # =========================================================================
    # Channel Configuration
    # =========================================================================

    def configure_dpch(
        self,
        spreading_factor: int = 64,
        slot_format: int = 11,
        dl_power_offset_db: float = 0.0,
    ) -> None:
        """
        Configure Dedicated Physical Channel (DPCH).

        Args:
            spreading_factor: Spreading factor (4, 8, 16, 32, 64, 128, 256)
            slot_format: Slot format number
            dl_power_offset_db: DL power offset relative to CPICH
        """
        self.scpi.write(f"{self.CONF_PREFIX}:DL:DPCh:SFACtor SF{spreading_factor}")
        self.scpi.write(f"{self.CONF_PREFIX}:DL:DPCh:SLOTformat {slot_format}")
        self.scpi.write(f"{self.CONF_PREFIX}:DL:DPCh:POWer:OFFSet {dl_power_offset_db}")

    def configure_r99_data(
        self,
        dl_rate_kbps: int = 384,
        ul_rate_kbps: int = 384,
    ) -> None:
        """
        Configure R99 (Release 99) data rates.

        Args:
            dl_rate_kbps: Downlink data rate in kbps (12.2, 64, 128, 384)
            ul_rate_kbps: Uplink data rate in kbps
        """
        logger.info(f"Configuring R99 data: DL={dl_rate_kbps}k, UL={ul_rate_kbps}k")

        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:DCH:DL:RATe K{dl_rate_kbps}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:DCH:UL:RATe K{ul_rate_kbps}")

    # =========================================================================
    # Measurements
    # =========================================================================

    def measure_tx_power(self) -> WCDMATxPowerResult:
        """
        Measure UE TX power levels.

        Returns:
            WCDMATxPowerResult with power measurements
        """
        logger.info("Measuring TX power")

        # Initiate measurement
        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:POWer:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        # Read results
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:POWer:AVERage?")
        parts = result.as_list()

        return WCDMATxPowerResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            dpcch_power_dbm=float(parts[2]) if len(parts) > 2 else float('nan'),
            dpdch_power_dbm=float(parts[3]) if len(parts) > 3 else float('nan'),
            total_power_dbm=float(parts[4]) if len(parts) > 4 else float('nan'),
        )

    def measure_aclr(self) -> Dict[str, float]:
        """
        Measure Adjacent Channel Leakage Ratio.

        Returns:
            Dictionary with ACLR measurements
        """
        logger.info("Measuring ACLR")

        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:ACLR:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:ACLR?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "aclr_minus_5mhz_db": float(parts[2]) if len(parts) > 2 else float('nan'),
            "aclr_plus_5mhz_db": float(parts[3]) if len(parts) > 3 else float('nan'),
            "aclr_minus_10mhz_db": float(parts[4]) if len(parts) > 4 else float('nan'),
            "aclr_plus_10mhz_db": float(parts[5]) if len(parts) > 5 else float('nan'),
        }

    def measure_evm(self) -> Dict[str, float]:
        """
        Measure Error Vector Magnitude.

        Returns:
            Dictionary with EVM measurements
        """
        logger.info("Measuring EVM")

        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:MODulation:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:MODulation:AVERage?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "evm_rms_percent": float(parts[2]) if len(parts) > 2 else float('nan'),
            "evm_peak_percent": float(parts[3]) if len(parts) > 3 else float('nan'),
            "magnitude_error_db": float(parts[4]) if len(parts) > 4 else float('nan'),
            "phase_error_deg": float(parts[5]) if len(parts) > 5 else float('nan'),
        }

    def measure_ber(self, duration_s: float = 10.0) -> WCDMABerResult:
        """
        Measure Bit Error Rate and Block Error Rate.

        Args:
            duration_s: Measurement duration in seconds

        Returns:
            WCDMABerResult with BER/BLER measurements
        """
        logger.info(f"Measuring BER/BLER for {duration_s}s")

        # Configure measurement duration
        self.scpi.write(f"{self.CONF_PREFIX}:MEAS:BER:TIMeout {duration_s}")

        # Start measurement
        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:BER:STATe ON")
        self.scpi.wait_for_completion(timeout=duration_s + 10)

        # Fetch results
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:BER?")
        parts = result.as_list()

        return WCDMABerResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            ber=float(parts[1]) if len(parts) > 1 else float('nan'),
            bler=float(parts[2]) if len(parts) > 2 else float('nan'),
            num_bits=int(float(parts[3])) if len(parts) > 3 else 0,
            num_blocks=int(float(parts[4])) if len(parts) > 4 else 0,
        )

    def measure_frequency_error(self) -> Dict[str, float]:
        """
        Measure UE frequency error.

        Returns:
            Dictionary with frequency error measurements
        """
        logger.info("Measuring frequency error")

        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:FREQuency:STATe ON")
        self.scpi.wait_for_completion(timeout=10)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:FREQuency?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "frequency_error_hz": float(parts[1]) if len(parts) > 1 else float('nan'),
            "frequency_error_ppm": float(parts[2]) if len(parts) > 2 else float('nan'),
        }

    # =========================================================================
    # CS Voice Call
    # =========================================================================

    def setup_voice_call(self, codec: str = "AMR122") -> None:
        """
        Set up a circuit-switched voice call.

        Args:
            codec: Voice codec (AMR122, AMR102, AMR795, AMR74, AMR67, AMR59, AMR515, AMR475)
        """
        logger.info(f"Setting up voice call with {codec}")

        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:VOICe:CODec {codec}")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:VOICe:STARt")
        time.sleep(2)

    def end_voice_call(self) -> None:
        """End the current voice call."""
        logger.info("Ending voice call")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:VOICe:STOP")

    # =========================================================================
    # PS Data
    # =========================================================================

    def setup_ps_data(self, apn: str = "test") -> None:
        """
        Set up packet-switched data connection.

        Args:
            apn: Access Point Name
        """
        logger.info(f"Setting up PS data with APN: {apn}")

        self.scpi.write(f'{self.CONF_PREFIX}:CONNection:APN "{apn}"')
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:PSData:STARt")

    def get_throughput(self) -> Dict[str, float]:
        """
        Get current data throughput.

        Returns:
            Dictionary with DL/UL throughput in kbps
        """
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:THRoughput?")
        parts = result.as_list()

        return {
            "dl_throughput_kbps": float(parts[1]) if len(parts) > 1 else 0,
            "ul_throughput_kbps": float(parts[2]) if len(parts) > 2 else 0,
        }
