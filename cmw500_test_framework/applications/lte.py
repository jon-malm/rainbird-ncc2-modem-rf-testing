"""
LTE Signaling Module

Controls LTE signaling functionality on the CMW500, including:
- Cell configuration and control
- Connection management
- Power level settings
- Measurements (TX power, ACLR, EVM, etc.)

SCPI Command Reference:
- CONFigure:LTE:SIGN:... - Configuration commands
- SOURce:LTE:SIGN:... - Source/generator commands
- READ/FETCh/MEASure:LTE:SIGN:... - Measurement commands
"""

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from ..core.client import CMW500Client

logger = logging.getLogger(__name__)


class LTEBandwidth(Enum):
    """LTE channel bandwidth options."""
    BW_1_4 = 1.4
    BW_3 = 3
    BW_5 = 5
    BW_10 = 10
    BW_15 = 15
    BW_20 = 20


class LTEDuplexMode(Enum):
    """LTE duplex mode."""
    FDD = "FDD"
    TDD = "TDD"


class LTECellState(Enum):
    """LTE cell state."""
    OFF = "OFF"
    ON = "ON"


class LTEConnectionState(Enum):
    """LTE signaling connection state."""
    OFF = "OFF"
    IDLE = "IDLE"
    ATTACHING = "ATT"
    CONNECTED = "CEST"
    REGISTERED = "REG"


class LTETransmissionMode(Enum):
    """LTE transmission modes (TM1-TM10)."""
    TM1 = 1  # Single antenna
    TM2 = 2  # Transmit diversity
    TM3 = 3  # Open-loop spatial multiplexing
    TM4 = 4  # Closed-loop spatial multiplexing
    TM5 = 5  # Multi-user MIMO
    TM6 = 6  # Closed-loop rank-1 precoding
    TM7 = 7  # Single-layer beamforming
    TM8 = 8  # Dual-layer beamforming
    TM9 = 9  # Up to 8 layer transmission
    TM10 = 10  # Up to 8 layer transmission (CoMP)


@dataclass
class LTECellConfig:
    """LTE cell configuration parameters."""
    band: int
    bandwidth_mhz: float
    duplex_mode: str
    dl_earfcn: int
    cell_id: int
    rs_epre_dbm: float
    pbch_power_dbm: float
    transmission_mode: int


@dataclass
class LTEMeasurementResult:
    """LTE measurement result container."""
    reliability: str
    out_of_tolerance: bool
    value: float
    unit: str

    @property
    def is_valid(self) -> bool:
        return self.reliability == "OK" or self.reliability == "0"


@dataclass
class LTETxPowerResult:
    """LTE TX power measurement results."""
    reliability: str
    pusch_power_dbm: float
    pucch_power_dbm: float
    srs_power_dbm: float
    prach_power_dbm: float


class LTESignaling:
    """
    LTE Signaling control for CMW500.

    Provides high-level methods for:
    - Cell configuration (band, bandwidth, power levels)
    - Cell state control (on/off)
    - Connection establishment
    - Downlink/uplink power control
    - Measurements

    Example:
        >>> client = CMW500Client("192.168.1.100")
        >>> client.connect()
        >>>
        >>> # Configure and enable cell
        >>> client.lte.configure_cell(band=1, bandwidth_mhz=10)
        >>> client.lte.set_dl_power(rs_epre_dbm=-85)
        >>> client.lte.cell_on()
        >>>
        >>> # Wait for UE to attach
        >>> client.lte.wait_for_attach(timeout=60)
        >>>
        >>> # Perform measurements
        >>> tx_power = client.lte.measure_tx_power()
        >>> print(f"PUSCH Power: {tx_power.pusch_power_dbm} dBm")
    """

    # SCPI subsystem prefixes
    CONF_PREFIX = "CONFigure:LTE:SIGN"
    SOURCE_PREFIX = "SOURce:LTE:SIGN"
    MEAS_PREFIX = "MEASure:LTE:SIGN"
    FETCH_PREFIX = "FETCh:LTE:SIGN"
    READ_PREFIX = "READ:LTE:SIGN"

    def __init__(self, client: "CMW500Client"):
        """
        Initialize LTE signaling module.

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
        bandwidth_mhz: float = 10.0,
        duplex_mode: str = "FDD",
        dl_earfcn: Optional[int] = None,
        cell_id: int = 1,
    ) -> None:
        """
        Configure basic LTE cell parameters.

        Args:
            band: LTE band number (1-85)
            bandwidth_mhz: Channel bandwidth (1.4, 3, 5, 10, 15, 20)
            duplex_mode: "FDD" or "TDD"
            dl_earfcn: Downlink EARFCN (auto-calculated if None)
            cell_id: Physical cell ID (0-503)
        """
        logger.info(f"Configuring LTE cell: Band {band}, BW {bandwidth_mhz} MHz")

        # Set duplex mode (must be done with cell off)
        self.scpi.write(f"{self.CONF_PREFIX}:DMODe {duplex_mode}")

        # Set band
        self.scpi.write(f"{self.CONF_PREFIX}:BAND OB{band}")

        # Set bandwidth
        bw_map = {1.4: "B014", 3: "B030", 5: "B050", 10: "B100", 15: "B150", 20: "B200"}
        bw_str = bw_map.get(bandwidth_mhz, "B100")
        self.scpi.write(f"{self.CONF_PREFIX}:CELL:BANDwidth:DL {bw_str}")
        self.scpi.write(f"{self.CONF_PREFIX}:CELL:BANDwidth:UL {bw_str}")

        # Set EARFCN if specified
        if dl_earfcn is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:CHANnel:DL {dl_earfcn}")

        # Set cell ID
        self.scpi.write(f"{self.CONF_PREFIX}:CELL:PCID {cell_id}")

        self.scpi.wait_for_completion()

    def configure_from_config(self) -> None:
        """Configure cell from client's config object."""
        if not self._client.config:
            raise ValueError("No configuration loaded")

        cfg = self._client.config.lte
        self.configure_cell(
            band=cfg.band,
            bandwidth_mhz=cfg.bandwidth_mhz,
            duplex_mode=cfg.duplex_mode,
            dl_earfcn=cfg.dl_earfcn,
            cell_id=cfg.cell_id,
        )
        self.set_dl_power(
            rs_epre_dbm=cfg.rs_epre_dbm,
            pbch_power_dbm=cfg.pbch_power_dbm,
        )
        self.set_transmission_mode(cfg.transmission_mode)

    def get_cell_config(self) -> Dict[str, any]:
        """
        Query current cell configuration.

        Returns:
            Dictionary with current cell parameters
        """
        return {
            "duplex_mode": self.scpi.query(f"{self.CONF_PREFIX}:DMODe?").value,
            "band": self.scpi.query(f"{self.CONF_PREFIX}:BAND?").value,
            "dl_bandwidth": self.scpi.query(f"{self.CONF_PREFIX}:CELL:BANDwidth:DL?").value,
            "ul_bandwidth": self.scpi.query(f"{self.CONF_PREFIX}:CELL:BANDwidth:UL?").value,
            "dl_earfcn": self.scpi.query(f"{self.CONF_PREFIX}:RFSettings:CHANnel:DL?").value,
            "cell_id": self.scpi.query(f"{self.CONF_PREFIX}:CELL:PCID?").value,
        }

    # =========================================================================
    # Cell State Control
    # =========================================================================

    def cell_on(self) -> None:
        """Turn on the LTE cell."""
        logger.info("Turning LTE cell ON")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:STATe ON")
        self._wait_for_cell_state("ON", timeout=30)

    def cell_off(self) -> None:
        """Turn off the LTE cell."""
        logger.info("Turning LTE cell OFF")
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
            if state == "ON" and target_state == "ON":
                return True
            time.sleep(0.5)
        raise TimeoutError(f"Cell did not reach state {target_state} within {timeout}s")

    # =========================================================================
    # Power Level Control
    # =========================================================================

    def set_dl_power(
        self,
        rs_epre_dbm: float = -85.0,
        pbch_power_dbm: Optional[float] = None,
        ocng_power_dbm: Optional[float] = None,
    ) -> None:
        """
        Set downlink power levels.

        Args:
            rs_epre_dbm: RS EPRE power in dBm/15kHz (typically -85 to -50)
            pbch_power_dbm: PBCH power (defaults to RS EPRE if None)
            ocng_power_dbm: OCNG power for unused RBs
        """
        logger.info(f"Setting DL power: RS EPRE = {rs_epre_dbm} dBm")

        self.scpi.write(f"{self.CONF_PREFIX}:RFSettings:DL:EPRe:LEVel {rs_epre_dbm}")

        if pbch_power_dbm is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:DL:PBCHpower:LEVel {pbch_power_dbm}")

        if ocng_power_dbm is not None:
            self.scpi.write(f"{self.CONF_PREFIX}:DL:OCNG:POWer {ocng_power_dbm}")

    def get_dl_power(self) -> Dict[str, float]:
        """Get current downlink power settings."""
        return {
            "rs_epre_dbm": self.scpi.query(
                f"{self.CONF_PREFIX}:RFSettings:DL:EPRe:LEVel?"
            ).as_float(),
        }

    def set_ul_power_control(
        self,
        p0_nominal_pusch: float = -96,
        p0_nominal_pucch: float = -96,
        alpha: float = 1.0,
    ) -> None:
        """
        Configure uplink power control parameters.

        Args:
            p0_nominal_pusch: P0 nominal for PUSCH
            p0_nominal_pucch: P0 nominal for PUCCH
            alpha: Path loss compensation factor (0-1)
        """
        self.scpi.write(f"{self.CONF_PREFIX}:UL:PUSCh:TPC:P0NP {p0_nominal_pusch}")
        self.scpi.write(f"{self.CONF_PREFIX}:UL:PUCCh:TPC:P0NP {p0_nominal_pucch}")
        self.scpi.write(f"{self.CONF_PREFIX}:UL:PUSCh:TPC:ALPHa {alpha}")

    # =========================================================================
    # MIMO Configuration
    # =========================================================================

    def set_transmission_mode(self, tm: int) -> None:
        """
        Set LTE transmission mode.

        Args:
            tm: Transmission mode (1-10)
        """
        if tm < 1 or tm > 10:
            raise ValueError(f"Invalid transmission mode: {tm}")
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:TRANsmission:MODE TM{tm}")
        logger.info(f"Set transmission mode to TM{tm}")

    def get_transmission_mode(self) -> int:
        """Get current transmission mode."""
        result = self.scpi.query(f"{self.CONF_PREFIX}:CONNection:TRANsmission:MODE?").value
        return int(result.replace("TM", ""))

    def configure_mimo(
        self,
        antenna_config: str = "1x1",
        transmission_mode: int = 1,
    ) -> None:
        """
        Configure MIMO settings.

        Args:
            antenna_config: "1x1", "2x2", "4x2", "4x4", "8x2"
            transmission_mode: LTE transmission mode
        """
        logger.info(f"Configuring MIMO: {antenna_config}, TM{transmission_mode}")

        # Map antenna config to SCPI parameter
        ant_map = {
            "1x1": "A1T1",
            "2x2": "A2T2",
            "4x2": "A4T2",
            "4x4": "A4T4",
            "8x2": "A8T2",
        }
        ant_param = ant_map.get(antenna_config, "A1T1")

        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:ANTenna:CONFig {ant_param}")
        self.set_transmission_mode(transmission_mode)

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
            True if UE attached, False if timeout

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
        Wait for RRC connected state (data connection established).

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if connected
        """
        logger.info("Waiting for RRC connected state...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            state = self.get_connection_state()
            if "CEST" in state:
                logger.info("RRC connection established")
                return True
            time.sleep(1)

        raise TimeoutError(f"RRC connection not established within {timeout}s")

    def disconnect_ue(self) -> None:
        """Disconnect UE from the cell (release RRC connection)."""
        logger.info("Disconnecting UE")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:RELease")
        time.sleep(1)

    def detach_ue(self) -> None:
        """Force UE detach."""
        logger.info("Detaching UE")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CELL:DETach")
        time.sleep(2)

    # =========================================================================
    # Measurements
    # =========================================================================

    def configure_measurement(
        self,
        measurement_type: str,
        repetitions: int = 1,
        averaging: int = 10,
    ) -> None:
        """
        Configure measurement parameters.

        Args:
            measurement_type: "POWer", "ACLR", "MODulation", etc.
            repetitions: Number of measurement repetitions
            averaging: Averaging count
        """
        # Configure repetition mode
        self.scpi.write(f"{self.CONF_PREFIX}:MEAS:{measurement_type}:REPetition SING")
        self.scpi.write(f"{self.CONF_PREFIX}:MEAS:{measurement_type}:SCOunt {averaging}")

    def measure_tx_power(self) -> LTETxPowerResult:
        """
        Measure UE TX power levels.

        Returns:
            LTETxPowerResult with power measurements
        """
        logger.info("Measuring TX power")

        # Initiate measurement
        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:POWer:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        # Read results
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:POWer:AVERage?")
        parts = result.as_list()

        # Parse result: reliability, out_of_tol, PUSCH, PUCCH, SRS, PRACH
        return LTETxPowerResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            pusch_power_dbm=float(parts[2]) if len(parts) > 2 else float('nan'),
            pucch_power_dbm=float(parts[3]) if len(parts) > 3 else float('nan'),
            srs_power_dbm=float(parts[4]) if len(parts) > 4 else float('nan'),
            prach_power_dbm=float(parts[5]) if len(parts) > 5 else float('nan'),
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
            "utra_minus_1": float(parts[2]) if len(parts) > 2 else float('nan'),
            "utra_plus_1": float(parts[3]) if len(parts) > 3 else float('nan'),
            "eutra_minus_1": float(parts[4]) if len(parts) > 4 else float('nan'),
            "eutra_plus_1": float(parts[5]) if len(parts) > 5 else float('nan'),
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
        }

    def measure_spectrum_flatness(self) -> Dict[str, float]:
        """
        Measure spectrum emission mask / flatness.

        Returns:
            Dictionary with spectrum measurements
        """
        logger.info("Measuring spectrum flatness")

        self.scpi.write(f"{self.MEAS_PREFIX}:MEAS:MEValuation:SEMask:STATe ON")
        self.scpi.wait_for_completion(timeout=30)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:MEValuation:SEMask?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "margin_low_db": float(parts[2]) if len(parts) > 2 else float('nan'),
            "margin_high_db": float(parts[3]) if len(parts) > 3 else float('nan'),
        }

    # =========================================================================
    # Data Throughput
    # =========================================================================

    def configure_data_connection(
        self,
        apn: str = "test",
        ip_type: str = "IPV4",
    ) -> None:
        """
        Configure data connection parameters.

        Args:
            apn: Access Point Name
            ip_type: "IPV4", "IPV6", or "IPV4V6"
        """
        self.scpi.write(f'{self.CONF_PREFIX}:CONNection:APN "{apn}"')
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:IPVersion {ip_type}")

    def get_throughput_stats(self) -> Dict[str, float]:
        """
        Get current throughput statistics.

        Returns:
            Dictionary with DL/UL throughput
        """
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:THRoughput?")
        parts = result.as_list()

        return {
            "dl_throughput_kbps": float(parts[1]) if len(parts) > 1 else 0,
            "ul_throughput_kbps": float(parts[2]) if len(parts) > 2 else 0,
        }

    # =========================================================================
    # Carrier Aggregation (LTE-A)
    # =========================================================================

    def configure_carrier_aggregation(
        self,
        num_dl_carriers: int = 2,
        num_ul_carriers: int = 1,
        scc_bands: Optional[List[int]] = None,
    ) -> None:
        """
        Configure carrier aggregation.

        Args:
            num_dl_carriers: Number of DL component carriers (1-8)
            num_ul_carriers: Number of UL component carriers (1-2)
            scc_bands: List of secondary component carrier bands
        """
        logger.info(f"Configuring CA: {num_dl_carriers}DL/{num_ul_carriers}UL")

        self.scpi.write(f"{self.CONF_PREFIX}:CELL:CAGG:DL:NCC {num_dl_carriers}")
        self.scpi.write(f"{self.CONF_PREFIX}:CELL:CAGG:UL:NCC {num_ul_carriers}")

        if scc_bands:
            for i, band in enumerate(scc_bands, start=2):
                self.scpi.write(f"{self.CONF_PREFIX}:CELL:CAGG:SCC{i}:BAND OB{band}")
