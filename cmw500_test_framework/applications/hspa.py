"""
HSPA (High Speed Packet Access) Module

Controls HSPA functionality on the CMW500, including:
- HSDPA (High Speed Downlink Packet Access) - 3.5G
- HSUPA (High Speed Uplink Packet Access) - 3.75G
- DC-HSDPA (Dual Carrier HSDPA)
- HSPA+ with 64QAM and MIMO

HSPA is an enhancement to WCDMA and uses the same RF configuration
but different transport channels for high-speed data.

SCPI Command Reference:
- CONFigure:WCDMa:SIGN:... - Base configuration (shared with WCDMA)
- CONFigure:WCDMa:SIGN:CONNection:HSDP... - HSDPA configuration
- CONFigure:WCDMa:SIGN:CONNection:HSUP... - HSUPA configuration
"""

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from ..core.client import CMW500Client

logger = logging.getLogger(__name__)


class HSDPACategory(Enum):
    """HSDPA UE category (determines max throughput)."""
    CAT_1 = 1     # 1.2 Mbps, 16QAM
    CAT_2 = 2     # 1.2 Mbps, 16QAM
    CAT_3 = 3     # 1.8 Mbps, 16QAM
    CAT_4 = 4     # 1.8 Mbps, 16QAM
    CAT_5 = 5     # 3.6 Mbps, 16QAM
    CAT_6 = 6     # 3.6 Mbps, 16QAM
    CAT_7 = 7     # 7.2 Mbps, 16QAM
    CAT_8 = 8     # 7.2 Mbps, 16QAM
    CAT_9 = 9     # 10.1 Mbps, 16QAM
    CAT_10 = 10   # 14.0 Mbps, 16QAM
    CAT_11 = 11   # 0.9 Mbps, QPSK only
    CAT_12 = 12   # 1.8 Mbps, QPSK only
    CAT_13 = 13   # 17.6 Mbps, 64QAM
    CAT_14 = 14   # 21.1 Mbps, 64QAM
    CAT_15 = 15   # 23.4 Mbps, 64QAM, MIMO
    CAT_16 = 16   # 28.0 Mbps, 64QAM, MIMO
    CAT_17 = 17   # 23.4 Mbps, 64QAM, MIMO
    CAT_18 = 18   # 28.0 Mbps, 64QAM, MIMO
    CAT_19 = 19   # 35.3 Mbps, 64QAM, MIMO
    CAT_20 = 20   # 42.2 Mbps, 64QAM, MIMO
    CAT_21 = 21   # 23.4 Mbps, 64QAM, DC
    CAT_22 = 22   # 28.0 Mbps, 64QAM, DC
    CAT_23 = 23   # 35.3 Mbps, 64QAM, DC
    CAT_24 = 24   # 42.2 Mbps, 64QAM, DC


class HSUPACategory(Enum):
    """HSUPA (E-DCH) UE category."""
    CAT_1 = 1     # 0.73 Mbps
    CAT_2 = 2     # 1.46 Mbps
    CAT_3 = 3     # 1.46 Mbps
    CAT_4 = 4     # 2.0 Mbps
    CAT_5 = 5     # 2.0 Mbps
    CAT_6 = 6     # 5.76 Mbps
    CAT_7 = 7     # 11.5 Mbps (16QAM)
    CAT_8 = 8     # 11.5 Mbps (16QAM)
    CAT_9 = 9     # 23.0 Mbps (16QAM, DC)


class HSDPAModulation(Enum):
    """HSDPA modulation schemes."""
    QPSK = "QPSK"
    QAM16 = "Q16"
    QAM64 = "Q64"


class HSUPAModulation(Enum):
    """HSUPA modulation schemes."""
    BPSK = "BPSK"
    QAM4 = "Q4"
    QAM16 = "Q16"


class CQIMode(Enum):
    """Channel Quality Indicator reporting mode."""
    FIXED = "FIX"
    REPORTED = "REP"
    AUTO = "AUTO"


@dataclass
class HSDPAConfig:
    """HSDPA configuration parameters."""
    category: int
    modulation: str
    num_codes: int
    cqi: int
    hs_scch_power_offset_db: float
    hs_pdsch_power_offset_db: float


@dataclass
class HSUPAConfig:
    """HSUPA configuration parameters."""
    category: int
    modulation: str
    tti_ms: int  # 2ms or 10ms TTI
    max_retransmissions: int
    e_tfci: int


@dataclass
class HSPAThroughputResult:
    """HSPA throughput measurement results."""
    reliability: str
    hsdpa_throughput_kbps: float
    hsupa_throughput_kbps: float
    hsdpa_bler_percent: float
    hsupa_bler_percent: float


@dataclass
class HSDPAMeasurementResult:
    """HSDPA specific measurement results."""
    reliability: str
    hs_dsch_power_dbm: float
    reported_cqi: int
    ack_ratio_percent: float
    nack_ratio_percent: float
    dtx_ratio_percent: float


class HSPASignaling:
    """
    HSPA (HSDPA/HSUPA) control for CMW500.

    Provides high-level methods for:
    - HSDPA configuration and data transfer
    - HSUPA configuration and data transfer
    - DC-HSDPA dual carrier operation
    - HSPA+ with 64QAM and MIMO
    - Throughput and BLER measurements

    Note: HSPA operates on top of WCDMA. The WCDMA cell must be
    configured and active before using HSPA features.

    Example:
        >>> client = CMW500Client("192.168.1.100")
        >>> client.connect()
        >>>
        >>> # First configure WCDMA cell
        >>> client.wcdma.configure_cell(band=1, uarfcn_dl=10700)
        >>> client.wcdma.cell_on()
        >>> client.wcdma.wait_for_attach(timeout=60)
        >>>
        >>> # Now configure and start HSPA
        >>> client.hspa.configure_hsdpa(category=10, modulation="Q16")
        >>> client.hspa.configure_hsupa(category=6)
        >>> client.hspa.start_hsdpa()
        >>> client.hspa.start_hsupa()
        >>>
        >>> # Measure throughput
        >>> result = client.hspa.measure_throughput()
        >>> print(f"DL: {result.hsdpa_throughput_kbps} kbps")
    """

    # SCPI subsystem prefixes (HSPA uses WCDMA subsystem)
    CONF_PREFIX = "CONFigure:WCDMa:SIGN"
    SOURCE_PREFIX = "SOURce:WCDMa:SIGN"
    MEAS_PREFIX = "MEASure:WCDMa:SIGN"
    FETCH_PREFIX = "FETCh:WCDMa:SIGN"

    def __init__(self, client: "CMW500Client"):
        """
        Initialize HSPA module.

        Args:
            client: CMW500Client instance
        """
        self._client = client

    @property
    def scpi(self):
        """Get SCPI connection."""
        return self._client.scpi

    # =========================================================================
    # HSDPA Configuration
    # =========================================================================

    def configure_hsdpa(
        self,
        category: int = 10,
        modulation: str = "Q16",
        num_codes: int = 15,
        cqi: int = 30,
        cqi_mode: str = "FIX",
    ) -> None:
        """
        Configure HSDPA (High Speed Downlink Packet Access).

        Args:
            category: HSDPA UE category (1-24)
            modulation: Modulation scheme (QPSK, Q16, Q64)
            num_codes: Number of HS-PDSCH codes (1-15)
            cqi: Channel Quality Indicator value (0-30)
            cqi_mode: CQI mode (FIX=fixed, REP=reported, AUTO=automatic)
        """
        logger.info(f"Configuring HSDPA: Cat {category}, {modulation}, {num_codes} codes")

        # Set UE category
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:UECategory {category}")

        # Set modulation
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:MODulation {modulation}")

        # Set number of codes
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:NCODes {num_codes}")

        # Set CQI mode and value
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:CQI:MODE {cqi_mode}")
        if cqi_mode == "FIX":
            self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:CQI:VALue {cqi}")

    def configure_hsdpa_power(
        self,
        hs_scch_power_offset_db: float = 0.0,
        hs_pdsch_power_offset_db: float = 0.0,
        hs_pdsch_total_power_db: float = -3.0,
    ) -> None:
        """
        Configure HSDPA power levels.

        Args:
            hs_scch_power_offset_db: HS-SCCH power offset from CPICH
            hs_pdsch_power_offset_db: HS-PDSCH power offset from CPICH
            hs_pdsch_total_power_db: Total HS-PDSCH power
        """
        self.scpi.write(
            f"{self.CONF_PREFIX}:CONNection:HSDPa:HSSC:POFFset {hs_scch_power_offset_db}"
        )
        self.scpi.write(
            f"{self.CONF_PREFIX}:CONNection:HSDPa:HSPD:POFFset {hs_pdsch_power_offset_db}"
        )
        self.scpi.write(
            f"{self.CONF_PREFIX}:CONNection:HSDPa:HSPD:TPOWer {hs_pdsch_total_power_db}"
        )

    def get_hsdpa_config(self) -> Dict[str, any]:
        """Get current HSDPA configuration."""
        return {
            "category": self.scpi.query(
                f"{self.CONF_PREFIX}:CONNection:HSDPa:UECategory?"
            ).value,
            "modulation": self.scpi.query(
                f"{self.CONF_PREFIX}:CONNection:HSDPa:MODulation?"
            ).value,
            "num_codes": self.scpi.query(
                f"{self.CONF_PREFIX}:CONNection:HSDPa:NCODes?"
            ).value,
            "cqi_mode": self.scpi.query(
                f"{self.CONF_PREFIX}:CONNection:HSDPa:CQI:MODE?"
            ).value,
        }

    # =========================================================================
    # HSUPA Configuration
    # =========================================================================

    def configure_hsupa(
        self,
        category: int = 6,
        tti_ms: int = 2,
        max_retransmissions: int = 4,
        modulation: str = "Q4",
    ) -> None:
        """
        Configure HSUPA (High Speed Uplink Packet Access / E-DCH).

        Args:
            category: HSUPA UE category (1-9)
            tti_ms: TTI duration (2 or 10 ms)
            max_retransmissions: Maximum HARQ retransmissions
            modulation: Modulation scheme (BPSK, Q4, Q16)
        """
        logger.info(f"Configuring HSUPA: Cat {category}, {tti_ms}ms TTI")

        # Set UE category
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSUPa:UECategory {category}")

        # Set TTI
        tti_param = "T2MS" if tti_ms == 2 else "T10MS"
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSUPa:TTI {tti_param}")

        # Set max retransmissions
        self.scpi.write(
            f"{self.CONF_PREFIX}:CONNection:HSUPa:HARQ:MRETransmissions {max_retransmissions}"
        )

        # Set modulation (for category 7+)
        if category >= 7:
            self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSUPa:MODulation {modulation}")

    def configure_hsupa_power(
        self,
        e_agch_power_offset_db: float = 0.0,
        e_rgch_power_offset_db: float = 0.0,
        e_hich_power_offset_db: float = 0.0,
    ) -> None:
        """
        Configure HSUPA power levels for E-DCH channels.

        Args:
            e_agch_power_offset_db: E-AGCH power offset
            e_rgch_power_offset_db: E-RGCH power offset
            e_hich_power_offset_db: E-HICH power offset
        """
        self.scpi.write(
            f"{self.CONF_PREFIX}:CONNection:HSUPa:EAGC:POFFset {e_agch_power_offset_db}"
        )
        self.scpi.write(
            f"{self.CONF_PREFIX}:CONNection:HSUPa:ERGC:POFFset {e_rgch_power_offset_db}"
        )
        self.scpi.write(
            f"{self.CONF_PREFIX}:CONNection:HSUPa:EHIC:POFFset {e_hich_power_offset_db}"
        )

    def get_hsupa_config(self) -> Dict[str, any]:
        """Get current HSUPA configuration."""
        return {
            "category": self.scpi.query(
                f"{self.CONF_PREFIX}:CONNection:HSUPa:UECategory?"
            ).value,
            "tti": self.scpi.query(
                f"{self.CONF_PREFIX}:CONNection:HSUPa:TTI?"
            ).value,
        }

    # =========================================================================
    # DC-HSDPA (Dual Carrier)
    # =========================================================================

    def configure_dc_hsdpa(
        self,
        enabled: bool = True,
        secondary_uarfcn: Optional[int] = None,
        secondary_scrambling_code: int = 0,
    ) -> None:
        """
        Configure DC-HSDPA (Dual Carrier HSDPA).

        Args:
            enabled: Enable/disable dual carrier
            secondary_uarfcn: UARFCN for secondary carrier
            secondary_scrambling_code: Scrambling code for secondary carrier
        """
        logger.info(f"Configuring DC-HSDPA: enabled={enabled}")

        state = "ON" if enabled else "OFF"
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:DCARrier:STATe {state}")

        if enabled and secondary_uarfcn is not None:
            self.scpi.write(
                f"{self.CONF_PREFIX}:CONNection:HSDPa:DCARrier:UARFCN {secondary_uarfcn}"
            )
            self.scpi.write(
                f"{self.CONF_PREFIX}:CONNection:HSDPa:DCARrier:SCRAMbling {secondary_scrambling_code}"
            )

    # =========================================================================
    # HSPA+ MIMO Configuration
    # =========================================================================

    def configure_mimo(
        self,
        enabled: bool = True,
        num_streams: int = 2,
    ) -> None:
        """
        Configure HSPA+ MIMO.

        Args:
            enabled: Enable/disable MIMO
            num_streams: Number of MIMO streams (1 or 2)
        """
        logger.info(f"Configuring HSPA+ MIMO: enabled={enabled}, streams={num_streams}")

        state = "ON" if enabled else "OFF"
        self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:MIMO:STATe {state}")

        if enabled:
            self.scpi.write(f"{self.CONF_PREFIX}:CONNection:HSDPa:MIMO:NSTReams {num_streams}")

    # =========================================================================
    # HSPA Data Transfer Control
    # =========================================================================

    def start_hsdpa(self) -> None:
        """Start HSDPA data transfer."""
        logger.info("Starting HSDPA")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:HSDPa:STARt")
        time.sleep(1)

    def stop_hsdpa(self) -> None:
        """Stop HSDPA data transfer."""
        logger.info("Stopping HSDPA")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:HSDPa:STOP")

    def start_hsupa(self) -> None:
        """Start HSUPA data transfer."""
        logger.info("Starting HSUPA")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:HSUPa:STARt")
        time.sleep(1)

    def stop_hsupa(self) -> None:
        """Stop HSUPA data transfer."""
        logger.info("Stopping HSUPA")
        self.scpi.write(f"{self.SOURCE_PREFIX}:CONNection:HSUPa:STOP")

    def get_hsdpa_state(self) -> str:
        """Get HSDPA connection state."""
        return self.scpi.query(f"{self.SOURCE_PREFIX}:CONNection:HSDPa:STATe?").value

    def get_hsupa_state(self) -> str:
        """Get HSUPA connection state."""
        return self.scpi.query(f"{self.SOURCE_PREFIX}:CONNection:HSUPa:STATe?").value

    # =========================================================================
    # Measurements
    # =========================================================================

    def measure_throughput(self) -> HSPAThroughputResult:
        """
        Measure HSPA data throughput.

        Returns:
            HSPAThroughputResult with throughput and BLER
        """
        logger.info("Measuring HSPA throughput")

        # Get throughput
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:THRoughput:HSDPa?")
        dl_parts = result.as_list()

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:THRoughput:HSUPa?")
        ul_parts = result.as_list()

        # Get BLER
        dl_bler = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:HSDPa:BLER?")
        dl_bler_parts = dl_bler.as_list()

        ul_bler = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:HSUPa:BLER?")
        ul_bler_parts = ul_bler.as_list()

        return HSPAThroughputResult(
            reliability=dl_parts[0] if len(dl_parts) > 0 else "NAV",
            hsdpa_throughput_kbps=float(dl_parts[1]) if len(dl_parts) > 1 else 0,
            hsupa_throughput_kbps=float(ul_parts[1]) if len(ul_parts) > 1 else 0,
            hsdpa_bler_percent=float(dl_bler_parts[1]) if len(dl_bler_parts) > 1 else 0,
            hsupa_bler_percent=float(ul_bler_parts[1]) if len(ul_bler_parts) > 1 else 0,
        )

    def measure_hsdpa_statistics(self) -> HSDPAMeasurementResult:
        """
        Measure HSDPA statistics including ACK/NACK ratios.

        Returns:
            HSDPAMeasurementResult with detailed statistics
        """
        logger.info("Measuring HSDPA statistics")

        # Fetch HS-DPCCH statistics
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:HSDPa:HSDPcch?")
        parts = result.as_list()

        return HSDPAMeasurementResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            hs_dsch_power_dbm=float(parts[1]) if len(parts) > 1 else float('nan'),
            reported_cqi=int(float(parts[2])) if len(parts) > 2 else 0,
            ack_ratio_percent=float(parts[3]) if len(parts) > 3 else 0,
            nack_ratio_percent=float(parts[4]) if len(parts) > 4 else 0,
            dtx_ratio_percent=float(parts[5]) if len(parts) > 5 else 0,
        )

    def measure_hsupa_power(self) -> Dict[str, float]:
        """
        Measure HSUPA (E-DCH) UE transmit power.

        Returns:
            Dictionary with E-DCH power measurements
        """
        logger.info("Measuring HSUPA power")

        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:HSUPa:POWer?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "e_dpcch_power_dbm": float(parts[1]) if len(parts) > 1 else float('nan'),
            "e_dpdch_power_dbm": float(parts[2]) if len(parts) > 2 else float('nan'),
            "total_power_dbm": float(parts[3]) if len(parts) > 3 else float('nan'),
        }

    def get_cqi_statistics(self) -> Dict[str, any]:
        """
        Get CQI (Channel Quality Indicator) statistics.

        Returns:
            Dictionary with CQI statistics
        """
        result = self.scpi.query(f"{self.FETCH_PREFIX}:MEAS:HSDPa:CQI?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "average_cqi": float(parts[1]) if len(parts) > 1 else 0,
            "min_cqi": int(float(parts[2])) if len(parts) > 2 else 0,
            "max_cqi": int(float(parts[3])) if len(parts) > 3 else 0,
        }

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_max_throughput(self, category: int, direction: str = "DL") -> float:
        """
        Get theoretical maximum throughput for a UE category.

        Args:
            category: UE category number
            direction: "DL" for HSDPA or "UL" for HSUPA

        Returns:
            Maximum throughput in Mbps
        """
        # HSDPA category max throughput (Mbps)
        hsdpa_max = {
            1: 1.2, 2: 1.2, 3: 1.8, 4: 1.8, 5: 3.6, 6: 3.6,
            7: 7.2, 8: 7.2, 9: 10.1, 10: 14.0, 11: 0.9, 12: 1.8,
            13: 17.6, 14: 21.1, 15: 23.4, 16: 28.0, 17: 23.4, 18: 28.0,
            19: 35.3, 20: 42.2, 21: 23.4, 22: 28.0, 23: 35.3, 24: 42.2,
        }

        # HSUPA category max throughput (Mbps)
        hsupa_max = {
            1: 0.73, 2: 1.46, 3: 1.46, 4: 2.0, 5: 2.0,
            6: 5.76, 7: 11.5, 8: 11.5, 9: 23.0,
        }

        if direction.upper() == "DL":
            return hsdpa_max.get(category, 0)
        else:
            return hsupa_max.get(category, 0)

    def configure_for_max_throughput(
        self,
        hsdpa_category: int = 10,
        hsupa_category: int = 6,
    ) -> None:
        """
        Configure HSPA for maximum throughput based on UE categories.

        Args:
            hsdpa_category: HSDPA UE category
            hsupa_category: HSUPA UE category
        """
        logger.info(f"Configuring for max throughput: HSDPA Cat{hsdpa_category}, "
                   f"HSUPA Cat{hsupa_category}")

        # Determine modulation based on category
        if hsdpa_category >= 13:
            dl_mod = "Q64"
        elif hsdpa_category in (11, 12):
            dl_mod = "QPSK"
        else:
            dl_mod = "Q16"

        ul_mod = "Q16" if hsupa_category >= 7 else "Q4"

        # Configure HSDPA
        self.configure_hsdpa(
            category=hsdpa_category,
            modulation=dl_mod,
            num_codes=15,
            cqi=30,
        )

        # Configure HSUPA
        self.configure_hsupa(
            category=hsupa_category,
            tti_ms=2,
            modulation=ul_mod,
        )

        # Enable MIMO for applicable categories
        if hsdpa_category >= 15:
            self.configure_mimo(enabled=True, num_streams=2)

        # Enable DC-HSDPA for applicable categories
        if hsdpa_category >= 21:
            self.configure_dc_hsdpa(enabled=True)
