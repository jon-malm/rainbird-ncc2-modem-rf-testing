"""
EC21 Test Configuration

Defines test scenarios for deterministic testing of the Quectel EC21 modem.

Quectel EC21 Specifications:
- LTE Cat 1: 10 Mbps DL, 5 Mbps UL
- LTE Bands: B1, B3, B5, B7, B8, B20, B28 (varies by variant)
- WCDMA/HSPA: 384 kbps (R99), up to 21 Mbps DL / 5.76 Mbps UL (HSPA+)
- WCDMA Bands: B1, B2, B5, B8
- GSM/GPRS/EDGE: Quad-band (850/900/1800/1900 MHz)
- EDGE: Up to 236.8 kbps
- GPRS: Up to 85.6 kbps

Test Philosophy:
- Distance simulation: Controlled via RS EPRE / CPICH / BCCH power levels
- Congestion simulation: Controlled via resource allocation, interference, SNR
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class Technology(Enum):
    """Supported technologies for EC21."""
    LTE = "LTE"
    HSPA = "HSPA"
    WCDMA = "WCDMA"
    GPRS = "GPRS"
    EDGE = "EDGE"
    GSM = "GSM"


@dataclass
class DistanceScenario:
    """
    Simulated distance scenario.

    Distance is simulated by adjusting the downlink power level.
    Path loss increases with distance according to propagation models.
    """
    name: str
    description: str
    distance_km: float
    # Power levels for each technology (dBm)
    lte_rs_epre_dbm: float      # LTE Reference Signal EPRE
    wcdma_cpich_dbm: float      # WCDMA Common Pilot Channel
    gsm_bcch_dbm: float         # GSM Broadcast Control Channel
    # Expected path loss (for reference)
    estimated_path_loss_db: float
    # Expected RSRP/RSCP/RXLEV ranges
    expected_lte_rsrp_range: Tuple[float, float]
    expected_wcdma_rscp_range: Tuple[float, float]
    expected_gsm_rxlev_range: Tuple[int, int]


@dataclass
class CongestionScenario:
    """
    Simulated channel congestion scenario.

    Congestion is simulated by:
    - LTE: Reducing PRB allocation, adding AWGN
    - HSPA: Reducing codes/category, adding interference
    - GPRS: Reducing timeslots, adding co-channel interference
    """
    name: str
    description: str
    congestion_level: str  # "none", "light", "moderate", "heavy", "extreme"
    # LTE parameters
    lte_prb_allocation_percent: int    # % of PRBs allocated to UE
    lte_mcs_limit: Optional[int]       # Max MCS index (None = auto)
    lte_awgn_snr_db: float             # SNR with AWGN enabled
    # HSPA parameters
    hspa_num_codes: int                # HS-PDSCH codes (1-15)
    hspa_category: int                 # HSDPA category
    # GPRS/EDGE parameters
    gprs_dl_timeslots: int             # Downlink timeslots (1-4)
    gprs_ul_timeslots: int             # Uplink timeslots (1-2)
    gprs_coding_scheme: str            # CS1-CS4 for GPRS, MCS1-9 for EDGE
    # Expected throughput ranges (kbps)
    expected_lte_dl_range: Tuple[float, float]
    expected_hspa_dl_range: Tuple[float, float]
    expected_gprs_dl_range: Tuple[float, float]


# =============================================================================
# Predefined Distance Scenarios
# =============================================================================
# Based on free-space path loss model at ~1950 MHz (Band 1/2)
# FSPL = 32.45 + 20*log10(f_MHz) + 20*log10(d_km)

DISTANCE_SCENARIOS: Dict[str, DistanceScenario] = {
    "very_close": DistanceScenario(
        name="very_close",
        description="Very close to tower (~100m), excellent signal",
        distance_km=0.1,
        lte_rs_epre_dbm=-50.0,
        wcdma_cpich_dbm=-40.0,
        gsm_bcch_dbm=-40.0,
        estimated_path_loss_db=58.0,
        expected_lte_rsrp_range=(-60, -50),
        expected_wcdma_rscp_range=(-50, -40),
        expected_gsm_rxlev_range=(50, 63),
    ),
    "close": DistanceScenario(
        name="close",
        description="Close to tower (~500m), very good signal",
        distance_km=0.5,
        lte_rs_epre_dbm=-65.0,
        wcdma_cpich_dbm=-55.0,
        gsm_bcch_dbm=-55.0,
        estimated_path_loss_db=72.0,
        expected_lte_rsrp_range=(-75, -65),
        expected_wcdma_rscp_range=(-65, -55),
        expected_gsm_rxlev_range=(40, 50),
    ),
    "medium": DistanceScenario(
        name="medium",
        description="Medium distance (~2km), good signal",
        distance_km=2.0,
        lte_rs_epre_dbm=-80.0,
        wcdma_cpich_dbm=-70.0,
        gsm_bcch_dbm=-70.0,
        estimated_path_loss_db=84.0,
        expected_lte_rsrp_range=(-90, -80),
        expected_wcdma_rscp_range=(-80, -70),
        expected_gsm_rxlev_range=(25, 35),
    ),
    "far": DistanceScenario(
        name="far",
        description="Far from tower (~5km), moderate signal",
        distance_km=5.0,
        lte_rs_epre_dbm=-95.0,
        wcdma_cpich_dbm=-85.0,
        gsm_bcch_dbm=-85.0,
        estimated_path_loss_db=92.0,
        expected_lte_rsrp_range=(-105, -95),
        expected_wcdma_rscp_range=(-95, -85),
        expected_gsm_rxlev_range=(10, 20),
    ),
    "very_far": DistanceScenario(
        name="very_far",
        description="Very far from tower (~10km), weak signal",
        distance_km=10.0,
        lte_rs_epre_dbm=-105.0,
        wcdma_cpich_dbm=-95.0,
        gsm_bcch_dbm=-95.0,
        estimated_path_loss_db=98.0,
        expected_lte_rsrp_range=(-115, -105),
        expected_wcdma_rscp_range=(-105, -95),
        expected_gsm_rxlev_range=(0, 10),
    ),
    "cell_edge": DistanceScenario(
        name="cell_edge",
        description="Cell edge (~15km), marginal signal",
        distance_km=15.0,
        lte_rs_epre_dbm=-115.0,
        wcdma_cpich_dbm=-105.0,
        gsm_bcch_dbm=-100.0,
        estimated_path_loss_db=102.0,
        expected_lte_rsrp_range=(-125, -115),
        expected_wcdma_rscp_range=(-115, -105),
        expected_gsm_rxlev_range=(-5, 5),
    ),
}


# =============================================================================
# Predefined Congestion Scenarios
# =============================================================================

CONGESTION_SCENARIOS: Dict[str, CongestionScenario] = {
    "none": CongestionScenario(
        name="none",
        description="No congestion - full resources available",
        congestion_level="none",
        # LTE: Full allocation
        lte_prb_allocation_percent=100,
        lte_mcs_limit=None,
        lte_awgn_snr_db=30.0,
        # HSPA: Full codes, high category
        hspa_num_codes=15,
        hspa_category=10,  # EC21 is Cat 1, but test at higher
        # GPRS: Max timeslots
        gprs_dl_timeslots=4,
        gprs_ul_timeslots=2,
        gprs_coding_scheme="CS4",
        # Expected throughput
        expected_lte_dl_range=(8000, 10000),    # ~10 Mbps max for Cat 1
        expected_hspa_dl_range=(3000, 7200),    # Depends on category
        expected_gprs_dl_range=(50, 85),        # CS4 max ~21.4 kbps/slot
    ),
    "light": CongestionScenario(
        name="light",
        description="Light congestion - minor resource reduction",
        congestion_level="light",
        lte_prb_allocation_percent=75,
        lte_mcs_limit=20,
        lte_awgn_snr_db=25.0,
        hspa_num_codes=12,
        hspa_category=8,
        gprs_dl_timeslots=3,
        gprs_ul_timeslots=2,
        gprs_coding_scheme="CS4",
        expected_lte_dl_range=(5000, 8000),
        expected_hspa_dl_range=(2000, 5000),
        expected_gprs_dl_range=(40, 65),
    ),
    "moderate": CongestionScenario(
        name="moderate",
        description="Moderate congestion - noticeable resource reduction",
        congestion_level="moderate",
        lte_prb_allocation_percent=50,
        lte_mcs_limit=15,
        lte_awgn_snr_db=20.0,
        hspa_num_codes=8,
        hspa_category=6,
        gprs_dl_timeslots=2,
        gprs_ul_timeslots=1,
        gprs_coding_scheme="CS3",
        expected_lte_dl_range=(3000, 5000),
        expected_hspa_dl_range=(1000, 3000),
        expected_gprs_dl_range=(20, 40),
    ),
    "heavy": CongestionScenario(
        name="heavy",
        description="Heavy congestion - significant resource limitation",
        congestion_level="heavy",
        lte_prb_allocation_percent=25,
        lte_mcs_limit=10,
        lte_awgn_snr_db=15.0,
        hspa_num_codes=4,
        hspa_category=4,
        gprs_dl_timeslots=1,
        gprs_ul_timeslots=1,
        gprs_coding_scheme="CS2",
        expected_lte_dl_range=(1000, 3000),
        expected_hspa_dl_range=(500, 1500),
        expected_gprs_dl_range=(10, 20),
    ),
    "extreme": CongestionScenario(
        name="extreme",
        description="Extreme congestion - minimal resources, high interference",
        congestion_level="extreme",
        lte_prb_allocation_percent=10,
        lte_mcs_limit=5,
        lte_awgn_snr_db=10.0,
        hspa_num_codes=2,
        hspa_category=2,
        gprs_dl_timeslots=1,
        gprs_ul_timeslots=1,
        gprs_coding_scheme="CS1",
        expected_lte_dl_range=(200, 1000),
        expected_hspa_dl_range=(100, 500),
        expected_gprs_dl_range=(5, 12),
    ),
}


@dataclass
class EC21TestConfig:
    """
    Complete test configuration for EC21 modem testing.
    """
    # CMW500 connection
    cmw500_host: str = "192.168.1.100"
    cmw500_port: int = 5025
    cmw500_timeout: float = 30.0

    # LTE configuration
    lte_band: int = 1
    lte_bandwidth_mhz: float = 10.0
    lte_earfcn: int = 300

    # WCDMA configuration
    wcdma_band: int = 1
    wcdma_uarfcn: int = 10700

    # GSM configuration
    gsm_band: str = "GSM900"
    gsm_arfcn: int = 50

    # Test parameters
    measurement_timeout_s: float = 30.0
    attach_timeout_s: float = 60.0
    data_transfer_duration_s: float = 10.0
    measurement_averaging: int = 10

    # Scenarios to test
    distance_scenarios: List[str] = field(default_factory=lambda: list(DISTANCE_SCENARIOS.keys()))
    congestion_scenarios: List[str] = field(default_factory=lambda: list(CONGESTION_SCENARIOS.keys()))

    # Technologies to test
    technologies: List[str] = field(default_factory=lambda: ["LTE", "HSPA", "GPRS"])

    # Output configuration
    output_dir: str = "./test_results"
    generate_report: bool = True


@dataclass
class TestResult:
    """Individual test result."""
    technology: str
    distance_scenario: str
    congestion_scenario: str
    timestamp: str
    # Connection metrics
    attach_success: bool
    attach_time_s: float
    # Signal quality
    signal_strength_dbm: float
    signal_quality: float  # RSRQ/Ec/No/BER depending on tech
    # Throughput
    dl_throughput_kbps: float
    ul_throughput_kbps: float
    # Error rates
    bler_percent: float
    # Pass/fail based on expected ranges
    passed: bool
    notes: str = ""


@dataclass
class TestSuiteResult:
    """Complete test suite results."""
    config: EC21TestConfig
    start_time: str
    end_time: str
    results: List[TestResult] = field(default_factory=list)
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed_tests / self.total_tests) * 100


# =============================================================================
# EC21 Specific Limits
# =============================================================================

EC21_LIMITS = {
    "LTE": {
        "max_dl_throughput_kbps": 10000,  # Cat 1 limit
        "max_ul_throughput_kbps": 5000,
        "min_rsrp_dbm": -120,  # Below this, connection may fail
        "target_bler_percent": 10,
    },
    "HSPA": {
        "max_dl_throughput_kbps": 21000,  # HSPA+ limit
        "max_ul_throughput_kbps": 5760,   # HSUPA Cat 6
        "min_rscp_dbm": -115,
        "target_bler_percent": 10,
    },
    "GPRS": {
        "max_dl_throughput_kbps": 85.6,   # 4 slots * CS4
        "max_ul_throughput_kbps": 42.8,   # 2 slots * CS4
        "min_rxlev": -110,  # dBm
        "target_ber_percent": 2.44,  # Class II BER limit
    },
    "EDGE": {
        "max_dl_throughput_kbps": 236.8,  # 4 slots * MCS9
        "max_ul_throughput_kbps": 118.4,
        "min_rxlev": -110,
        "target_ber_percent": 2.44,
    },
}
