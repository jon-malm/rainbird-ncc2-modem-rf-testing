"""
GSM/GPRS/EDGE Signaling Module

Controls GSM (2G) signaling functionality on the CMW500, including:
- Cell configuration and control
- Circuit-switched (CS) voice calls
- GPRS packet data (2.5G)
- EDGE enhanced data rates (2.75G)
- Power level settings
- Measurements (TX power, PVT, phase/frequency error)

SCPI Command Reference:
- CONFigure:GSM:SIGN:... - Configuration commands
- SOURce:GSM:SIGN:... - Source/generator commands
- READ/FETCh/MEASure:GSM:SIGN:... - Measurement commands
"""

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from ..core.client import CMW500Client

logger = logging.getLogger(__name__)


class GSMBand(Enum):
    """GSM frequency bands."""
    GSM850 = "G850"      # 850 MHz (Americas)
    GSM900 = "G900"      # 900 MHz (Europe, Asia)
    EGSM900 = "GE900"    # Extended GSM 900
    GSM1800 = "G1800"    # DCS 1800 MHz
    GSM1900 = "G1900"    # PCS 1900 MHz (Americas)


class GSMCellState(Enum):
    """GSM cell state."""
    OFF = "OFF"
    ON = "ON"


class GSMConnectionState(Enum):
    """GSM signaling connection state."""
    OFF = "OFF"
    IDLE = "IDLE"
    ATTACHING = "ATT"
    CONNECTED = "CEST"
    REGISTERED = "REG"


class GSMModulation(Enum):
    """GSM modulation schemes."""
    GMSK = "GMSK"      # Gaussian Minimum Shift Keying (GSM/GPRS)
    PSK8 = "P8SK"      # 8-PSK (EDGE)


class GPRSCodingScheme(Enum):
    """GPRS coding schemes."""
    CS1 = "CS1"    # 9.05 kbps
    CS2 = "CS2"    # 13.4 kbps
    CS3 = "CS3"    # 15.6 kbps
    CS4 = "CS4"    # 21.4 kbps


class EDGECodingScheme(Enum):
    """EDGE (EGPRS) modulation and coding schemes."""
    MCS1 = "MCS1"   # 8.8 kbps (GMSK)
    MCS2 = "MCS2"   # 11.2 kbps (GMSK)
    MCS3 = "MCS3"   # 14.8 kbps (GMSK)
    MCS4 = "MCS4"   # 17.6 kbps (GMSK)
    MCS5 = "MCS5"   # 22.4 kbps (8-PSK)
    MCS6 = "MCS6"   # 29.6 kbps (8-PSK)
    MCS7 = "MCS7"   # 44.8 kbps (8-PSK)
    MCS8 = "MCS8"   # 54.4 kbps (8-PSK)
    MCS9 = "MCS9"   # 59.2 kbps (8-PSK)


@dataclass
class GSMCellConfig:
    """GSM cell configuration parameters."""
    band: str
    arfcn: int
    bsic: int
    bcch_level_dbm: float
    tch_level_dbm: float


@dataclass
class GSMTxPowerResult:
    """GSM TX power measurement results."""
    reliability: str
    burst_power_dbm: float
    mean_power_dbm: float
    peak_power_dbm: float


@dataclass
class GSMPVTResult:
    """GSM Power vs Time (burst timing) measurement results."""
    reliability: str
    rise_time_us: float
    fall_time_us: float
    useful_part_dbm: float
    timing_advance_bits: int


@dataclass
class GSMModulationResult:
    """GSM modulation quality measurement results."""
    reliability: str
    phase_error_rms_deg: float
    phase_error_peak_deg: float
    frequency_error_hz: float
    evm_rms_percent: Optional[float] = None  # For EDGE only


class GSMSignaling:
    """
    GSM/GPRS/EDGE Signaling control for CMW500.

    Provides high-level methods for:
    - Cell configuration (band, ARFCN, BSIC, power levels)
    - Cell state control (on/off)
    - Circuit-switched voice calls
    - GPRS/EDGE packet data connections
    - Measurements (TX power, PVT, modulation quality)

    Example:
        >>> client = CMW500Client("192.168.1.100")
        >>> client.connect()
        >>>
        >>> # Configure and enable cell
        >>> client.gsm.configure_cell(band="GSM900", arfcn=50)
        >>> client.gsm.set_dl_power(bcch_level_dbm=-60)
        >>> client.gsm.cell_on()
        >>>
        >>> # Wait for UE to attach
        >>> client.gsm.wait_for_attach(timeout=60)
        >>>
        >>> # Make a voice call
        >>> client.gsm.setup_voice_call()
        >>>
        >>> # Perform measurements
        >>> tx_power = client.gsm.measure_tx_power()
        >>> print(f"Burst Power: {tx_power.burst_power_dbm} dBm")
    """

    # SCPI subsystem prefixes
    CONF_PREFIX = "CONFigure:GSM:SIGN"
    SOURCE_PREFIX = "SOURce:GSM:SIGN"
    MEAS_PREFIX = "MEASure:GSM:SIGN"
    FETCH_PREFIX = "FETCh:GSM:SIGN"
    READ_PREFIX = "READ:GSM:SIGN"

    def __init__(self, client: "CMW500Client"):
        """
        Initialize GSM signaling module.

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
        band: str = "GSM900",
        arfcn: int = 50,
        bsic: int = 1,
        bcch_level_dbm: float = -60.0,
    ) -> None:
        """
        Configure basic GSM cell parameters.

        Args:
            band: GSM band ("GSM850", "GSM900", "EGSM900", "GSM1800", "GSM1900")
            arfcn: Absolute Radio Frequency Channel Number
            bsic: Base Station Identity Code (0-63)
            bcch_level_dbm: BCCH power level in dBm
        """
        logger.info(f"Configuring GSM cell: {band}, ARFCN {arfcn}")

        # Map band string to SCPI parameter
        band_map = {
            "GSM850": "G850",
            "GSM900": "G900",
            "EGSM900": "GE900",
            "GSM1800": "G1800",
            "GSM1900": "G1900",
        }
        band_param = band_map.get(band.upper(), band)

        # Set band
        self.scpi.write(f"{self.CONF_PREFIX}:BAND {band_param}")

        # Set ARFCN
        self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:CHANnel:BCCH {arfcn}")

        # Set BSIC
        self.scpi.write(f"{self.CONF_PREFIX}:CELL:BSIC {bsic}")

        # Set BCCH power
        self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:LEVel:BCCH {bcch_level_dbm}")

        self.scpi.wait_for_completion()

    def get_cell_config(self) -> Dict[str, any]:
        """
        Query current cell configuration.

        Returns:
            Dictionary with current cell parameters
        """
        return {
            "band": self.scpi.query(f"{self.CONF_PREFIX}:BAND?").value,
            "arfcn": self.scpi.query(f"{self.CONF_PREFIX}:RFSettings:CHANnel:BCCH?").value,
            "bsic": self.scpi.query(f"{self.CONF_PREFIX}:CELL:BSIC?").value,
            "bcch_level": self.scpi.query(f"{self.CONF_PREFIX}:RFSettings:LEVel:BCCH?").value,
        }

    # =========================================================================
    # Cell State Control
    # =========================================================================

    def cell_on(self) -> None:
        """Turn on the GSM cell."""
        logger.info("Turning GSM cell ON")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:STATe ON")
        self._wait_for_cell_state("ON", timeout=30)

    def cell_off(self) -> None:
        """Turn off the GSM cell."""
        logger.info("Turning GSM cell OFF")
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
        bcch_level_dbm: float = -60.0,
        tch_level_dbm: Optional[float] = None,
        pdtch_level_dbm: Optional[float] = None,
    ) -> None:
        """
        Set downlink power levels.

        Args:
            bcch_level_dbm: BCCH power in dBm
            tch_level_dbm: TCH (traffic channel) power in dBm
            pdtch_level_dbm: PDTCH (packet data) power in dBm
        """
        logger.info(f"Setting DL power: BCCH = {bcch_level_dbm} dBm")

        self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:LEVel:BCCH {bcch_level_dbm}")

        if tch_level_dbm is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:LEVel:TCH {tch_level_dbm}")

        if pdtch_level_dbm is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:LEVel:PDTCH {pdtch_level_dbm}")

    def set_ul_power_control(
        self,
        power_control_level: int = 5,
        gamma: int = 0,
    ) -> None:
        """
        Configure uplink power control parameters.

        Args:
            power_control_level: MS power control level (0-31)
            gamma: Power control parameter gamma
        """
        self.scpi.write(f"{self.CONF_PREFIX}:MS:PCLevel {power_control_level}")
        self.scpi.write(f"{self.CONF_PREFIX}:MS:GAMMa {gamma}")

    def get_dl_power(self) -> Dict[str, float]:
        """Get current downlink power settings."""
        return {
            "bcch_level_dbm": self.scpi.query(
                f"{self.CONF_PREFIX}:RFSettings:LEVel:BCCH?"
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
        Wait for MS to attach to the cell.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if MS attached

        Raises:
            TimeoutError: If timeout exceeded
        """
        logger.info("Waiting for MS to attach...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            state = self.get_connection_state()
            logger.debug(f"Connection state: {state}")

            if "ATT" in state or "REG" in state or "CEST" in state:
                logger.info("MS attached successfully")
                return True

            time.sleep(1)

        raise TimeoutError(f"MS did not attach within {timeout}s")

    def disconnect_ms(self) -> None:
        """Disconnect MS from the cell."""
        logger.info("Disconnecting MS")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:RELease")
        time.sleep(1)

    # =========================================================================
    # CS Voice Call
    # =========================================================================

    def setup_voice_call(
        self,
        codec: str = "FR",
        tch_arfcn: Optional[int] = None,
        timeslot: int = 3,
    ) -> None:
        """
        Set up a circuit-switched voice call.

        Args:
            codec: Voice codec (FR=Full Rate, HR=Half Rate, EFR=Enhanced Full Rate)
            tch_arfcn: Traffic channel ARFCN (None=same as BCCH)
            timeslot: Timeslot number (0-7)
        """
        logger.info(f"Setting up voice call with {codec} codec")

        # Set codec
        codec_map = {"FR": "FR", "HR": "HR", "EFR": "EFR", "AMR_FR": "AMF", "AMR_HR": "AMH"}
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:SPEech:CODec {codec_map.get(codec, codec)}")

        # Set TCH ARFCN if specified
        if tch_arfcn is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:CHANnel:TCH {tch_arfcn}")

        # Set timeslot
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:TCH:TSLot {timeslot}")

        # Start call
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:SPEech:STARt")
        time.sleep(2)

    def end_voice_call(self) -> None:
        """End the current voice call."""
        logger.info("Ending voice call")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:SPEech:STOP")

    def get_call_state(self) -> str:
        """Get current call state."""
        return self.scpi.query(f"{self.SOURCE_PREFIX}:CONNection:SPEech:STATe?").value

    # =========================================================================
    # GPRS Configuration
    # =========================================================================

    def configure_gprs(
        self,
        multislot_class: int = 12,
        coding_scheme: str = "CS4",
        dl_timeslots: int = 4,
        ul_timeslots: int = 2,
    ) -> None:
        """
        Configure GPRS packet data parameters.

        Args:
            multislot_class: GPRS multislot class (1-45)
            coding_scheme: Coding scheme (CS1, CS2, CS3, CS4)
            dl_timeslots: Number of downlink timeslots (1-8)
            ul_timeslots: Number of uplink timeslots (1-8)
        """
        logger.info(f"Configuring GPRS: MS class {multislot_class}, {coding_scheme}")

        self.scpi.write(f"{self.CONF_PREFIX}:MS:MSLClass {multislot_class}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:GPRS:DL:CSCheme {coding_scheme}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:GPRS:UL:CSCheme {coding_scheme}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:GPRS:DL:TSLots {dl_timeslots}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:GPRS:UL:TSLots {ul_timeslots}")

    def attach_gprs(self, apn: str = "test") -> None:
        """
        Perform GPRS attach.

        Args:
            apn: Access Point Name
        """
        logger.info(f"Performing GPRS attach with APN: {apn}")

        self.scpi.write(f'{self.CONF_PREFIX}:CONNection:APN "{apn}"')
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:GPRS:ATTach")

    def activate_pdp_context(self) -> None:
        """Activate PDP context for data transfer."""
        logger.info("Activating PDP context")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:GPRS:PDPContext:ACTivate")
        time.sleep(2)

    def deactivate_pdp_context(self) -> None:
        """Deactivate PDP context."""
        logger.info("Deactivating PDP context")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:GPRS:PDPContext:DEACtivate")

    def detach_gprs(self) -> None:
        """Perform GPRS detach."""
        logger.info("Performing GPRS detach")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:GPRS:DETach")

    # =========================================================================
    # EDGE Configuration
    # =========================================================================

    def configure_edge(
        self,
        multislot_class: int = 12,
        mcs_dl: str = "MCS9",
        mcs_ul: str = "MCS9",
        dl_timeslots: int = 4,
        ul_timeslots: int = 2,
    ) -> None:
        """
        Configure EDGE (EGPRS) packet data parameters.

        Args:
            multislot_class: EGPRS multislot class
            mcs_dl: Downlink modulation and coding scheme (MCS1-MCS9)
            mcs_ul: Uplink modulation and coding scheme (MCS1-MCS9)
            dl_timeslots: Number of downlink timeslots
            ul_timeslots: Number of uplink timeslots
        """
        logger.info(f"Configuring EDGE: MS class {multislot_class}, DL:{mcs_dl}, UL:{mcs_ul}")

        self.scpi.write(f"{self.CONF_PREFIX}:MS:MSLClass {multislot_class}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:EGPRS:DL:MCSCheme {mcs_dl}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:EGPRS:UL:MCSCheme {mcs_ul}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:EGPRS:DL:TSLots {dl_timeslots}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:EGPRS:UL:TSLots {ul_timeslots}")

    def attach_edge(self, apn: str = "test") -> None:
        """
        Perform EDGE/EGPRS attach.

        Args:
            apn: Access Point Name
        """
        logger.info(f"Performing EDGE attach with APN: {apn}")

        self.scpi.write(f'{self.CONF_PREFIX}:CONNection:APN "{apn}"')
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:EGPRS:ATTach")

    # =========================================================================
    # Measurements
    # =========================================================================

    def measure_tx_power(self) -> GSMTxPowerResult:
        """
        Measure MS TX power levels.

        Returns:
            GSMTxPowerResult with power measurements
        """
        logger.info("Measuring TX power")

        # Initiate measurement
        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:POWer:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        # Read results
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:POWer:AVERage?")
        parts = result.as_list()

        return GSMTxPowerResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            burst_power_dbm=float(parts[1]) if len(parts) > 1 else float('nan'),
            mean_power_dbm=float(parts[2]) if len(parts) > 2 else float('nan'),
            peak_power_dbm=float(parts[3]) if len(parts) > 3 else float('nan'),
        )

    def measure_pvt(self) -> GSMPVTResult:
        """
        Measure Power vs Time (burst shape/timing).

        Returns:
            GSMPVTResult with timing measurements
        """
        logger.info("Measuring PVT")

        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:PVTime:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:PVTime:AVERage?")
        parts = result.as_list()

        return GSMPVTResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            rise_time_us=float(parts[1]) if len(parts) > 1 else float('nan'),
            fall_time_us=float(parts[2]) if len(parts) > 2 else float('nan'),
            useful_part_dbm=float(parts[3]) if len(parts) > 3 else float('nan'),
            timing_advance_bits=int(float(parts[4])) if len(parts) > 4 else 0,
        )

    def measure_modulation(self) -> GSMModulationResult:
        """
        Measure modulation quality (phase/frequency error).

        Returns:
            GSMModulationResult with modulation measurements
        """
        logger.info("Measuring modulation quality")

        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:MODulation:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:MODulation:AVERage?")
        parts = result.as_list()

        mod_result = GSMModulationResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            phase_error_rms_deg=float(parts[1]) if len(parts) > 1 else float('nan'),
            phase_error_peak_deg=float(parts[2]) if len(parts) > 2 else float('nan'),
            frequency_error_hz=float(parts[3]) if len(parts) > 3 else float('nan'),
        )

        # EVM is available for EDGE/8-PSK modulation
        if len(parts) > 4:
            mod_result.evm_rms_percent = float(parts[4])

        return mod_result

    def measure_spectrum(self) -> Dict[str, float]:
        """
        Measure spectrum due to modulation and switching.

        Returns:
            Dictionary with spectrum measurements
        """
        logger.info("Measuring spectrum")

        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:SPECtrum:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:SPECtrum:MODulation?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "mod_spectrum_200khz_db": float(parts[1]) if len(parts) > 1 else float('nan'),
            "mod_spectrum_250khz_db": float(parts[2]) if len(parts) > 2 else float('nan'),
            "mod_spectrum_400khz_db": float(parts[3]) if len(parts) > 3 else float('nan'),
        }

    def measure_ber(self, loops: int = 1000) -> Dict[str, float]:
        """
        Measure Bit Error Rate.

        Args:
            loops: Number of measurement loops

        Returns:
            Dictionary with BER measurements
        """
        logger.info(f"Measuring BER for {loops} loops")

        self.scpi.write(f"{self.CONF_PREFIX}:MEAS:BER:LOOPs {loops}")
        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:BER:STATe ON")
        self.scpi.wait_for_completion(timeout=60)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:BER?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "class_ii_ber": float(parts[1]) if len(parts) > 1 else float('nan'),
            "rber_ib": float(parts[2]) if len(parts) > 2 else float('nan'),
            "rber_ii": float(parts[3]) if len(parts) > 3 else float('nan'),
        }

    # =========================================================================
    # GPRS/EDGE Throughput
    # =========================================================================

    def get_throughput(self) -> Dict[str, float]:
        """
        Get current GPRS/EDGE data throughput.

        Returns:
            Dictionary with DL/UL throughput in kbps
        """
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:THRoughput?")
        parts = result.as_list()

        return {
            "dl_throughput_kbps": float(parts[1]) if len(parts) > 1 else 0,
            "ul_throughput_kbps": float(parts[2]) if len(parts) > 2 else 0,
        }

    # =========================================================================
    # Hopping Configuration
    # =========================================================================

    def configure_frequency_hopping(
        self,
        enabled: bool = False,
        hopping_sequence: str = "CYCLIC",
        ma_list: Optional[List[int]] = None,
    ) -> None:
        """
        Configure frequency hopping.

        Args:
            enabled: Enable/disable frequency hopping
            hopping_sequence: "CYCLIC" or "RANDOM"
            ma_list: Mobile Allocation list of ARFCNs
        """
        state = "ON" if enabled else "OFF"
        self.scpi.write(f"{self.CONF_PREFIX}:HOPPing:STATe {state}")

        if enabled:
            self.scpi.write(f"{self.CONF_PREFIX}:HOPPing:SEQuence {hopping_sequence}")

            if ma_list:
                ma_str = ",".join(str(a) for a in ma_list)
                self.scpi.write(f"{self.CONF_PREFIX}:HOPPing:MAList {ma_str}")
