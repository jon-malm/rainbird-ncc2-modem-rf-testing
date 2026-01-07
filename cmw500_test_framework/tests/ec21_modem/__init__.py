"""
Quectel EC21 Modem Deterministic Test Suite

Test configurations and scenarios for deterministic testing of:
- LTE (Cat 1)
- HSPA (WCDMA with high-speed data)
- GPRS (GSM packet data)

Under controlled conditions simulating:
- Distance to tower (via path loss / signal strength)
- Channel congestion (via resource allocation / interference)
- Carrier failover (AT&T, T-Mobile, Verizon)
"""

from .test_config import (
    EC21TestConfig,
    DistanceScenario,
    CongestionScenario,
    DISTANCE_SCENARIOS,
    CONGESTION_SCENARIOS,
)
from .lte_tests import EC21LTETestSuite
from .gprs_tests import EC21GPRSTestSuite
from .hspa_tests import EC21HSPATestSuite
from .carrier_config import (
    CarrierConfig,
    FailoverScenario,
    FailoverTestResult,
    CARRIER_CONFIGS,
    FAILOVER_SCENARIOS,
    get_carrier_config,
    get_all_carriers,
)
from .failover_tests import EC21FailoverTestSuite
from .test_runner import EC21TestRunner, main as run_tests

__all__ = [
    # Test configuration
    "EC21TestConfig",
    "DistanceScenario",
    "CongestionScenario",
    "DISTANCE_SCENARIOS",
    "CONGESTION_SCENARIOS",
    # Technology test suites
    "EC21LTETestSuite",
    "EC21GPRSTestSuite",
    "EC21HSPATestSuite",
    # Carrier failover
    "CarrierConfig",
    "FailoverScenario",
    "FailoverTestResult",
    "CARRIER_CONFIGS",
    "FAILOVER_SCENARIOS",
    "get_carrier_config",
    "get_all_carriers",
    "EC21FailoverTestSuite",
    # Test runner
    "EC21TestRunner",
    "run_tests",
]
