"""
US Carrier Configuration for EC21 Modem Testing

Defines network parameters for AT&T, T-Mobile, and Verizon
for use in carrier failover testing.

Quectel EC21 US Carrier Band Support:
- EC21-A (AT&T/T-Mobile): LTE B2/B4/B5/B12, WCDMA B2/B4/B5
- EC21-V (Verizon): LTE B4/B13, WCDMA B2/B5
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class Carrier(Enum):
    """US mobile carriers."""
    ATT = "AT&T"
    TMOBILE = "T-Mobile"
    VERIZON = "Verizon"


class FailoverTrigger(Enum):
    """Triggers for carrier failover."""
    SIGNAL_LOSS = "signal_loss"           # Complete signal loss
    SIGNAL_DEGRADATION = "signal_degradation"  # Signal below threshold
    NETWORK_REJECT = "network_reject"     # Network rejects registration
    DATA_STALL = "data_stall"             # Data connection stalled
    MANUAL = "manual"                     # Manual carrier switch


@dataclass
class CarrierBandConfig:
    """Band configuration for a specific technology."""
    band: int
    earfcn: Optional[int] = None    # LTE E-UTRA ARFCN
    uarfcn: Optional[int] = None    # WCDMA UARFCN
    arfcn: Optional[int] = None     # GSM ARFCN
    bandwidth_mhz: float = 10.0     # LTE bandwidth


@dataclass
class CarrierConfig:
    """
    Complete carrier configuration for network simulation.
    """
    name: str
    carrier: Carrier

    # Network identifiers
    mcc: str                        # Mobile Country Code (US = 310, 311, 312)
    mnc: str                        # Mobile Network Code
    plmn: str                       # Combined MCC+MNC

    # LTE configuration
    lte_bands: List[CarrierBandConfig] = field(default_factory=list)
    lte_primary_band: int = 0

    # WCDMA/HSPA configuration
    wcdma_bands: List[CarrierBandConfig] = field(default_factory=list)
    wcdma_primary_band: int = 0

    # GSM configuration (if supported)
    gsm_bands: List[CarrierBandConfig] = field(default_factory=list)

    # APN configuration
    apn: str = "internet"
    apn_user: str = ""
    apn_password: str = ""

    # Typical signal levels in coverage area
    typical_rsrp_dbm: float = -85.0
    typical_rscp_dbm: float = -80.0

    # Priority (lower = higher priority for failover)
    priority: int = 1


# =============================================================================
# AT&T Configuration
# =============================================================================

ATT_CONFIG = CarrierConfig(
    name="AT&T",
    carrier=Carrier.ATT,
    mcc="310",
    mnc="410",
    plmn="310410",

    # LTE bands (most common for AT&T)
    lte_bands=[
        CarrierBandConfig(band=2, earfcn=875, bandwidth_mhz=10.0),    # PCS 1900 MHz
        CarrierBandConfig(band=4, earfcn=2175, bandwidth_mhz=10.0),   # AWS 1700/2100 MHz
        CarrierBandConfig(band=5, earfcn=2525, bandwidth_mhz=10.0),   # Cellular 850 MHz
        CarrierBandConfig(band=12, earfcn=5095, bandwidth_mhz=10.0),  # Lower 700 MHz
        CarrierBandConfig(band=17, earfcn=5780, bandwidth_mhz=10.0),  # Lower 700 MHz B/C
        CarrierBandConfig(band=66, earfcn=66486, bandwidth_mhz=10.0), # AWS-3
    ],
    lte_primary_band=2,

    # WCDMA bands
    wcdma_bands=[
        CarrierBandConfig(band=2, uarfcn=9662),   # PCS 1900 MHz
        CarrierBandConfig(band=5, uarfcn=4357),   # Cellular 850 MHz
    ],
    wcdma_primary_band=2,

    # GSM bands (AT&T still has some GSM)
    gsm_bands=[
        CarrierBandConfig(band=850, arfcn=190),   # GSM 850
        CarrierBandConfig(band=1900, arfcn=661),  # PCS 1900
    ],

    apn="broadband",
    typical_rsrp_dbm=-85.0,
    typical_rscp_dbm=-80.0,
    priority=1,
)


# =============================================================================
# T-Mobile Configuration
# =============================================================================

TMOBILE_CONFIG = CarrierConfig(
    name="T-Mobile",
    carrier=Carrier.TMOBILE,
    mcc="310",
    mnc="260",
    plmn="310260",

    # LTE bands (T-Mobile primary bands)
    lte_bands=[
        CarrierBandConfig(band=2, earfcn=900, bandwidth_mhz=15.0),    # PCS 1900 MHz
        CarrierBandConfig(band=4, earfcn=2000, bandwidth_mhz=15.0),   # AWS 1700/2100 MHz
        CarrierBandConfig(band=12, earfcn=5035, bandwidth_mhz=5.0),   # Lower 700 MHz
        CarrierBandConfig(band=66, earfcn=66536, bandwidth_mhz=20.0), # AWS-3
        CarrierBandConfig(band=71, earfcn=68586, bandwidth_mhz=10.0), # 600 MHz
    ],
    lte_primary_band=4,

    # WCDMA bands
    wcdma_bands=[
        CarrierBandConfig(band=2, uarfcn=9663),   # PCS 1900 MHz
        CarrierBandConfig(band=4, uarfcn=1537),   # AWS 1700/2100 MHz
    ],
    wcdma_primary_band=4,

    # T-Mobile shut down GSM in 2024
    gsm_bands=[],

    apn="fast.t-mobile.com",
    typical_rsrp_dbm=-82.0,
    typical_rscp_dbm=-78.0,
    priority=2,
)


# =============================================================================
# Verizon Configuration
# =============================================================================

VERIZON_CONFIG = CarrierConfig(
    name="Verizon",
    carrier=Carrier.VERIZON,
    mcc="311",
    mnc="480",
    plmn="311480",

    # LTE bands (Verizon primary bands)
    lte_bands=[
        CarrierBandConfig(band=2, earfcn=850, bandwidth_mhz=10.0),    # PCS 1900 MHz
        CarrierBandConfig(band=4, earfcn=2050, bandwidth_mhz=10.0),   # AWS 1700/2100 MHz
        CarrierBandConfig(band=5, earfcn=2560, bandwidth_mhz=10.0),   # Cellular 850 MHz
        CarrierBandConfig(band=13, earfcn=5230, bandwidth_mhz=10.0),  # Upper 700 MHz
        CarrierBandConfig(band=66, earfcn=66461, bandwidth_mhz=20.0), # AWS-3
    ],
    lte_primary_band=13,  # Band 13 is Verizon's primary LTE band

    # WCDMA bands (Verizon primarily CDMA, limited WCDMA via LTE roaming)
    wcdma_bands=[
        CarrierBandConfig(band=2, uarfcn=9662),
        CarrierBandConfig(band=5, uarfcn=4357),
    ],
    wcdma_primary_band=5,

    # Verizon has no GSM
    gsm_bands=[],

    apn="vzwinternet",
    typical_rsrp_dbm=-88.0,
    typical_rscp_dbm=-82.0,
    priority=3,
)


# =============================================================================
# Carrier Registry
# =============================================================================

CARRIER_CONFIGS: Dict[str, CarrierConfig] = {
    "att": ATT_CONFIG,
    "at&t": ATT_CONFIG,
    "tmobile": TMOBILE_CONFIG,
    "t-mobile": TMOBILE_CONFIG,
    "verizon": VERIZON_CONFIG,
    "vzw": VERIZON_CONFIG,
}


def get_carrier_config(carrier_name: str) -> Optional[CarrierConfig]:
    """
    Get carrier configuration by name.

    Args:
        carrier_name: Carrier name (case-insensitive)

    Returns:
        CarrierConfig or None if not found
    """
    return CARRIER_CONFIGS.get(carrier_name.lower().replace(" ", ""))


def get_all_carriers() -> List[CarrierConfig]:
    """Get all unique carrier configurations."""
    return [ATT_CONFIG, TMOBILE_CONFIG, VERIZON_CONFIG]


# =============================================================================
# Failover Scenarios
# =============================================================================

@dataclass
class FailoverScenario:
    """
    Defines a carrier failover test scenario.
    """
    name: str
    description: str

    # Carrier sequence (primary, secondary, tertiary)
    primary_carrier: str
    secondary_carrier: str
    tertiary_carrier: Optional[str] = None

    # Failover trigger configuration
    trigger: FailoverTrigger = FailoverTrigger.SIGNAL_LOSS

    # Signal thresholds
    signal_loss_rsrp_dbm: float = -140.0      # Signal considered "lost"
    degradation_rsrp_dbm: float = -115.0      # Signal degradation threshold

    # Timing parameters
    signal_ramp_time_s: float = 5.0           # Time to ramp signal down
    failover_timeout_s: float = 30.0          # Max time to complete failover
    recovery_time_s: float = 10.0             # Time before primary recovery

    # Expected behavior
    expected_failover_time_s: Tuple[float, float] = (5.0, 20.0)  # (min, max)
    expect_data_continuity: bool = False      # Should data session survive?


# Predefined failover scenarios
FAILOVER_SCENARIOS: Dict[str, FailoverScenario] = {
    # Primary carrier signal loss scenarios
    "att_to_tmobile_signal_loss": FailoverScenario(
        name="att_to_tmobile_signal_loss",
        description="AT&T signal loss, failover to T-Mobile",
        primary_carrier="att",
        secondary_carrier="tmobile",
        tertiary_carrier="verizon",
        trigger=FailoverTrigger.SIGNAL_LOSS,
        signal_loss_rsrp_dbm=-140.0,
        failover_timeout_s=30.0,
        expected_failover_time_s=(5.0, 25.0),
    ),

    "tmobile_to_att_signal_loss": FailoverScenario(
        name="tmobile_to_att_signal_loss",
        description="T-Mobile signal loss, failover to AT&T",
        primary_carrier="tmobile",
        secondary_carrier="att",
        tertiary_carrier="verizon",
        trigger=FailoverTrigger.SIGNAL_LOSS,
        signal_loss_rsrp_dbm=-140.0,
        failover_timeout_s=30.0,
        expected_failover_time_s=(5.0, 25.0),
    ),

    "verizon_to_att_signal_loss": FailoverScenario(
        name="verizon_to_att_signal_loss",
        description="Verizon signal loss, failover to AT&T",
        primary_carrier="verizon",
        secondary_carrier="att",
        tertiary_carrier="tmobile",
        trigger=FailoverTrigger.SIGNAL_LOSS,
        signal_loss_rsrp_dbm=-140.0,
        failover_timeout_s=30.0,
        expected_failover_time_s=(5.0, 25.0),
    ),

    # Signal degradation scenarios (more gradual)
    "att_to_tmobile_degradation": FailoverScenario(
        name="att_to_tmobile_degradation",
        description="AT&T signal degradation, failover to T-Mobile",
        primary_carrier="att",
        secondary_carrier="tmobile",
        trigger=FailoverTrigger.SIGNAL_DEGRADATION,
        degradation_rsrp_dbm=-115.0,
        signal_ramp_time_s=10.0,
        failover_timeout_s=45.0,
        expected_failover_time_s=(10.0, 40.0),
    ),

    "tmobile_to_verizon_degradation": FailoverScenario(
        name="tmobile_to_verizon_degradation",
        description="T-Mobile signal degradation, failover to Verizon",
        primary_carrier="tmobile",
        secondary_carrier="verizon",
        trigger=FailoverTrigger.SIGNAL_DEGRADATION,
        degradation_rsrp_dbm=-115.0,
        signal_ramp_time_s=10.0,
        failover_timeout_s=45.0,
        expected_failover_time_s=(10.0, 40.0),
    ),

    # Network rejection scenarios
    "att_reject_to_tmobile": FailoverScenario(
        name="att_reject_to_tmobile",
        description="AT&T network reject, failover to T-Mobile",
        primary_carrier="att",
        secondary_carrier="tmobile",
        trigger=FailoverTrigger.NETWORK_REJECT,
        failover_timeout_s=20.0,
        expected_failover_time_s=(3.0, 15.0),
    ),

    # Triple failover (primary -> secondary -> tertiary)
    "triple_failover_att_first": FailoverScenario(
        name="triple_failover_att_first",
        description="AT&T -> T-Mobile -> Verizon triple failover",
        primary_carrier="att",
        secondary_carrier="tmobile",
        tertiary_carrier="verizon",
        trigger=FailoverTrigger.SIGNAL_LOSS,
        failover_timeout_s=60.0,
        expected_failover_time_s=(10.0, 50.0),
    ),

    # Recovery scenarios (fail back to primary when restored)
    "att_recovery_from_tmobile": FailoverScenario(
        name="att_recovery_from_tmobile",
        description="Recover to AT&T after T-Mobile failover",
        primary_carrier="att",
        secondary_carrier="tmobile",
        trigger=FailoverTrigger.SIGNAL_LOSS,
        recovery_time_s=30.0,
        failover_timeout_s=60.0,
        expected_failover_time_s=(5.0, 25.0),
    ),

    # Data stall scenarios
    "att_data_stall_to_tmobile": FailoverScenario(
        name="att_data_stall_to_tmobile",
        description="AT&T data stall, failover to T-Mobile",
        primary_carrier="att",
        secondary_carrier="tmobile",
        trigger=FailoverTrigger.DATA_STALL,
        failover_timeout_s=45.0,
        expected_failover_time_s=(15.0, 40.0),
    ),
}


@dataclass
class FailoverTestResult:
    """Result of a carrier failover test."""
    scenario_name: str
    timestamp: str

    # Initial state
    primary_carrier: str
    primary_technology: str
    primary_band: int
    primary_rsrp_dbm: float

    # Failover result
    failover_triggered: bool
    failover_successful: bool
    failover_time_s: float

    # Final state
    final_carrier: str
    final_technology: str
    final_band: int
    final_rsrp_dbm: float

    # Data continuity
    data_session_maintained: bool
    data_interruption_time_s: float

    # Pass/fail
    passed: bool
    failure_reason: str = ""
    notes: str = ""


# =============================================================================
# EC21 Carrier Capabilities
# =============================================================================

# EC21-A variant (AT&T/T-Mobile optimized)
EC21_A_BANDS = {
    "lte": [2, 4, 5, 12],
    "wcdma": [2, 4, 5],
}

# EC21-V variant (Verizon optimized)
EC21_V_BANDS = {
    "lte": [4, 13],
    "wcdma": [2, 5],
}

# EC21-AUT variant (Australia, but sometimes used)
EC21_AUT_BANDS = {
    "lte": [1, 3, 5, 7, 8, 28],
    "wcdma": [1, 5, 8],
}


def get_ec21_supported_bands(variant: str = "A") -> Dict[str, List[int]]:
    """
    Get supported bands for EC21 variant.

    Args:
        variant: EC21 variant (A, V, AUT)

    Returns:
        Dict with 'lte' and 'wcdma' band lists
    """
    variants = {
        "A": EC21_A_BANDS,
        "V": EC21_V_BANDS,
        "AUT": EC21_AUT_BANDS,
    }
    return variants.get(variant.upper(), EC21_A_BANDS)


def is_band_supported(carrier_config: CarrierConfig, ec21_variant: str = "A") -> Dict[str, bool]:
    """
    Check if carrier bands are supported by EC21 variant.

    Args:
        carrier_config: Carrier configuration
        ec21_variant: EC21 variant

    Returns:
        Dict with technology compatibility info
    """
    supported = get_ec21_supported_bands(ec21_variant)

    lte_compatible = any(
        band.band in supported["lte"]
        for band in carrier_config.lte_bands
    )

    wcdma_compatible = any(
        band.band in supported["wcdma"]
        for band in carrier_config.wcdma_bands
    )

    return {
        "lte": lte_compatible,
        "wcdma": wcdma_compatible,
        "any": lte_compatible or wcdma_compatible,
    }
