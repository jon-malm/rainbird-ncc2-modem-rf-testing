#!/usr/bin/env python3
"""
EC21 GPRS/EDGE Test Suite

Deterministic GPRS and EDGE testing for Quectel EC21 modem under various
distance (signal strength) and congestion conditions.

EC21 GSM/GPRS/EDGE Capabilities:
- Quad-band: 850/900/1800/1900 MHz
- GPRS: Up to 85.6 kbps (Class 12, 4+2 slots, CS4)
- EDGE: Up to 236.8 kbps (Class 12, 4+2 slots, MCS9)
- Multislot Class 12 (4 DL + 2 UL, not simultaneous)
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import sys
sys.path.insert(0, str(__file__).rsplit("/", 4)[0])

from cmw500_test_framework import CMW500Client
from cmw500_test_framework.applications.network_simulation import NetworkSimulator
from .test_config import (
    EC21TestConfig,
    DistanceScenario,
    CongestionScenario,
    DISTANCE_SCENARIOS,
    CONGESTION_SCENARIOS,
    TestResult,
    EC21_LIMITS,
)

logger = logging.getLogger(__name__)


@dataclass
class GPRSTestParameters:
    """GPRS-specific test parameters derived from scenarios."""
    # Cell configuration
    band: str
    arfcn: int
    bsic: int
    # Power
    bcch_level_dbm: float
    tch_level_dbm: float
    # Congestion simulation
    dl_timeslots: int
    ul_timeslots: int
    coding_scheme: str  # CS1-CS4 for GPRS, MCS1-MCS9 for EDGE
    use_edge: bool
    # Expected results
    expected_dl_range: Tuple[float, float]
    expected_rxlev_range: Tuple[int, int]


class EC21GPRSTestSuite:
    """
    GPRS/EDGE test suite for EC21 modem.

    Tests GPRS and EDGE performance under controlled distance and
    congestion scenarios.

    Test Matrix:
    - 6 distance scenarios x 5 congestion scenarios = 30 test combinations
    - Each test measures: attach time, RXLEV, throughput, BER

    Example:
        >>> config = EC21TestConfig(cmw500_host="192.168.1.100")
        >>> suite = EC21GPRSTestSuite(config)
        >>> results = suite.run_all_tests()
    """

    def __init__(self, config: EC21TestConfig, use_edge: bool = False):
        """
        Initialize GPRS test suite.

        Args:
            config: Test configuration
            use_edge: If True, test EDGE; if False, test GPRS
        """
        self.config = config
        self.use_edge = use_edge
        self._client: Optional[CMW500Client] = None
        self._results: List[TestResult] = []

    def _connect(self) -> None:
        """Connect to CMW500."""
        if self._client is None or not self._client.connected:
            self._client = CMW500Client(
                host=self.config.cmw500_host,
                port=self.config.cmw500_port,
                timeout=self.config.cmw500_timeout,
            )
            self._client.connect()
            logger.info(f"Connected to CMW500: {self._client.get_identification()}")

    def _disconnect(self) -> None:
        """Disconnect from CMW500."""
        if self._client and self._client.connected:
            try:
                self._client.gsm.cell_off()
            except Exception:
                pass
            self._client.disconnect()
            self._client = None

    def _derive_parameters(
        self,
        distance: DistanceScenario,
        congestion: CongestionScenario,
    ) -> GPRSTestParameters:
        """
        Derive GPRS test parameters from distance and congestion scenarios.

        Args:
            distance: Distance scenario
            congestion: Congestion scenario

        Returns:
            GPRSTestParameters for the test
        """
        # Map congestion to EDGE MCS if using EDGE
        if self.use_edge:
            # Map GPRS coding scheme to EDGE MCS
            cs_to_mcs = {
                "CS1": "MCS1",
                "CS2": "MCS3",
                "CS3": "MCS5",
                "CS4": "MCS9",
            }
            coding = cs_to_mcs.get(congestion.gprs_coding_scheme, "MCS5")
        else:
            coding = congestion.gprs_coding_scheme

        return GPRSTestParameters(
            band=self.config.gsm_band,
            arfcn=self.config.gsm_arfcn,
            bsic=1,
            bcch_level_dbm=distance.gsm_bcch_dbm,
            tch_level_dbm=distance.gsm_bcch_dbm,  # Same as BCCH
            dl_timeslots=congestion.gprs_dl_timeslots,
            ul_timeslots=congestion.gprs_ul_timeslots,
            coding_scheme=coding,
            use_edge=self.use_edge,
            expected_dl_range=congestion.expected_gprs_dl_range,
            expected_rxlev_range=distance.expected_gsm_rxlev_range,
        )

    def _configure_cell(self, params: GPRSTestParameters) -> None:
        """
        Configure GSM cell with test parameters.

        Args:
            params: Test parameters
        """
        gsm = self._client.gsm

        logger.info(f"Configuring GSM: {params.band}, ARFCN {params.arfcn}, "
                   f"BCCH {params.bcch_level_dbm} dBm")

        # Basic cell configuration
        gsm.configure_cell(
            band=params.band,
            arfcn=params.arfcn,
            bsic=params.bsic,
            bcch_level_dbm=params.bcch_level_dbm,
        )

        # Set TCH power level
        gsm.set_dl_power(
            bcch_level_dbm=params.bcch_level_dbm,
            tch_level_dbm=params.tch_level_dbm,
            pdtch_level_dbm=params.tch_level_dbm,
        )

    def _configure_gprs(self, params: GPRSTestParameters) -> None:
        """
        Configure GPRS/EDGE data parameters.

        Args:
            params: Test parameters
        """
        gsm = self._client.gsm

        if params.use_edge:
            logger.info(f"Configuring EDGE: {params.dl_timeslots} DL slots, "
                       f"{params.ul_timeslots} UL slots, {params.coding_scheme}")
            gsm.configure_edge(
                multislot_class=12,  # EC21 is MS class 12
                mcs_dl=params.coding_scheme,
                mcs_ul=params.coding_scheme,
                dl_timeslots=params.dl_timeslots,
                ul_timeslots=params.ul_timeslots,
            )
        else:
            logger.info(f"Configuring GPRS: {params.dl_timeslots} DL slots, "
                       f"{params.ul_timeslots} UL slots, {params.coding_scheme}")
            gsm.configure_gprs(
                multislot_class=12,
                coding_scheme=params.coding_scheme,
                dl_timeslots=params.dl_timeslots,
                ul_timeslots=params.ul_timeslots,
            )

    def _measure_signal_quality(self) -> Dict[str, float]:
        """
        Query signal quality measurements.

        Returns:
            Dictionary with RXLEV and related metrics
        """
        try:
            dl_power = self._client.gsm.get_dl_power()
            return {
                "bcch_level_dbm": dl_power.get("bcch_level_dbm", float('nan')),
            }
        except Exception as e:
            logger.warning(f"Failed to measure signal quality: {e}")
            return {"bcch_level_dbm": float('nan')}

    def _measure_throughput(self) -> Dict[str, float]:
        """
        Measure GPRS/EDGE data throughput.

        Returns:
            Dictionary with DL and UL throughput in kbps
        """
        try:
            stats = self._client.gsm.get_throughput()
            return {
                "dl_throughput_kbps": stats.get("dl_throughput_kbps", 0),
                "ul_throughput_kbps": stats.get("ul_throughput_kbps", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to measure throughput: {e}")
            return {"dl_throughput_kbps": 0, "ul_throughput_kbps": 0}

    def _measure_ber(self) -> float:
        """
        Measure Bit Error Rate.

        Returns:
            BER percentage
        """
        try:
            result = self._client.gsm.measure_ber(loops=1000)
            return result.get("class_ii_ber", float('nan'))
        except Exception as e:
            logger.warning(f"Failed to measure BER: {e}")
            return float('nan')

    def run_single_test(
        self,
        distance_name: str,
        congestion_name: str,
    ) -> TestResult:
        """
        Run a single GPRS/EDGE test with specified scenarios.

        Args:
            distance_name: Name of distance scenario
            congestion_name: Name of congestion scenario

        Returns:
            TestResult with measurements
        """
        distance = DISTANCE_SCENARIOS[distance_name]
        congestion = CONGESTION_SCENARIOS[congestion_name]
        params = self._derive_parameters(distance, congestion)

        tech_name = "EDGE" if self.use_edge else "GPRS"
        logger.info(f"=" * 60)
        logger.info(f"{tech_name} Test: {distance_name} distance, {congestion_name} congestion")
        logger.info(f"=" * 60)

        result = TestResult(
            technology=tech_name,
            distance_scenario=distance_name,
            congestion_scenario=congestion_name,
            timestamp=datetime.now().isoformat(),
            attach_success=False,
            attach_time_s=0,
            signal_strength_dbm=float('nan'),
            signal_quality=float('nan'),
            dl_throughput_kbps=0,
            ul_throughput_kbps=0,
            bler_percent=float('nan'),
            passed=False,
        )

        try:
            self._connect()

            # Configure cell
            self._configure_cell(params)

            # Turn on cell
            logger.info("Starting GSM cell...")
            self._client.gsm.cell_on()

            # Wait for MS attachment
            logger.info("Waiting for MS attachment...")
            attach_start = time.time()
            try:
                self._client.gsm.wait_for_attach(timeout=self.config.attach_timeout_s)
                result.attach_success = True
                result.attach_time_s = time.time() - attach_start
                logger.info(f"MS attached in {result.attach_time_s:.1f}s")
            except TimeoutError:
                result.attach_success = False
                result.notes = "Attachment timeout"
                logger.warning("MS attachment timeout")
                return result

            # Measure signal quality
            signal = self._measure_signal_quality()
            result.signal_strength_dbm = signal.get("bcch_level_dbm", float('nan'))

            # Configure GPRS/EDGE
            self._configure_gprs(params)

            # Attach to GPRS
            logger.info("Attaching to GPRS...")
            try:
                if params.use_edge:
                    self._client.gsm.attach_edge(apn="test")
                else:
                    self._client.gsm.attach_gprs(apn="test")

                self._client.gsm.activate_pdp_context()
            except Exception as e:
                result.notes = f"GPRS attach failed: {e}"
                logger.warning(result.notes)
                return result

            # Allow time for data path setup
            time.sleep(3)

            # Measure throughput
            logger.info("Measuring throughput...")
            throughput = self._measure_throughput()
            result.dl_throughput_kbps = throughput["dl_throughput_kbps"]
            result.ul_throughput_kbps = throughput["ul_throughput_kbps"]
            logger.info(f"Throughput: DL={result.dl_throughput_kbps:.1f} kbps, "
                       f"UL={result.ul_throughput_kbps:.1f} kbps")

            # Measure BER
            result.bler_percent = self._measure_ber()

            # Determine pass/fail
            dl_min, dl_max = params.expected_dl_range
            limits = EC21_LIMITS["EDGE" if self.use_edge else "GPRS"]

            # Check if results are within expected ranges
            dl_ok = dl_min * 0.7 <= result.dl_throughput_kbps <= dl_max * 1.3  # 30% margin
            ber_ok = result.bler_percent <= limits["target_ber_percent"]

            result.passed = result.attach_success and dl_ok
            if not result.passed:
                if not dl_ok:
                    result.notes += f"DL throughput outside range [{dl_min}, {dl_max}]. "

            logger.info(f"Test {'PASSED' if result.passed else 'FAILED'}")

        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            result.notes = str(e)
            result.passed = False

        finally:
            # Clean up
            try:
                self._client.gsm.deactivate_pdp_context()
                self._client.gsm.detach_gprs()
                self._client.gsm.cell_off()
            except Exception:
                pass

        return result

    def run_all_tests(self) -> List[TestResult]:
        """
        Run all GPRS/EDGE tests across distance and congestion scenarios.

        Returns:
            List of TestResult objects
        """
        self._results = []
        tech_name = "EDGE" if self.use_edge else "GPRS"

        logger.info(f"Starting EC21 {tech_name} Test Suite")
        logger.info(f"Distance scenarios: {self.config.distance_scenarios}")
        logger.info(f"Congestion scenarios: {self.config.congestion_scenarios}")

        total_tests = len(self.config.distance_scenarios) * len(self.config.congestion_scenarios)
        test_num = 0

        try:
            self._connect()

            for dist_name in self.config.distance_scenarios:
                for cong_name in self.config.congestion_scenarios:
                    test_num += 1
                    logger.info(f"\n[Test {test_num}/{total_tests}]")

                    result = self.run_single_test(dist_name, cong_name)
                    self._results.append(result)

                    # Brief pause between tests
                    time.sleep(2)

        finally:
            self._disconnect()

        # Summary
        passed = sum(1 for r in self._results if r.passed)
        logger.info(f"\n{'=' * 60}")
        logger.info(f"{tech_name} Test Suite Complete: {passed}/{len(self._results)} passed")
        logger.info(f"{'=' * 60}")

        return self._results

    def run_distance_sweep(
        self,
        congestion_scenario: str = "none",
    ) -> List[TestResult]:
        """
        Run tests sweeping through all distance scenarios at fixed congestion.

        Args:
            congestion_scenario: Congestion level to use

        Returns:
            List of TestResult objects
        """
        results = []

        try:
            self._connect()

            for dist_name in self.config.distance_scenarios:
                result = self.run_single_test(dist_name, congestion_scenario)
                results.append(result)
                time.sleep(2)

        finally:
            self._disconnect()

        return results

    def run_congestion_sweep(
        self,
        distance_scenario: str = "medium",
    ) -> List[TestResult]:
        """
        Run tests sweeping through all congestion scenarios at fixed distance.

        Args:
            distance_scenario: Distance scenario to use

        Returns:
            List of TestResult objects
        """
        results = []

        try:
            self._connect()

            for cong_name in self.config.congestion_scenarios:
                result = self.run_single_test(distance_scenario, cong_name)
                results.append(result)
                time.sleep(2)

        finally:
            self._disconnect()

        return results


def main():
    """Run GPRS tests from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="EC21 GPRS/EDGE Test Suite")
    parser.add_argument("host", help="CMW500 IP address")
    parser.add_argument("--band", default="GSM900", help="GSM band")
    parser.add_argument("--arfcn", type=int, default=50, help="ARFCN")
    parser.add_argument("--edge", action="store_true", help="Test EDGE instead of GPRS")
    parser.add_argument("--distance", help="Single distance scenario to test")
    parser.add_argument("--congestion", help="Single congestion scenario to test")
    parser.add_argument("--sweep-distance", action="store_true",
                        help="Sweep all distance scenarios")
    parser.add_argument("--sweep-congestion", action="store_true",
                        help="Sweep all congestion scenarios")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # Create config
    config = EC21TestConfig(
        cmw500_host=args.host,
        gsm_band=args.band,
        gsm_arfcn=args.arfcn,
    )

    # Create test suite
    suite = EC21GPRSTestSuite(config, use_edge=args.edge)

    # Run tests
    if args.distance and args.congestion:
        results = [suite.run_single_test(args.distance, args.congestion)]
    elif args.sweep_distance:
        results = suite.run_distance_sweep(args.congestion or "none")
    elif args.sweep_congestion:
        results = suite.run_congestion_sweep(args.distance or "medium")
    else:
        results = suite.run_all_tests()

    # Print summary
    tech = "EDGE" if args.edge else "GPRS"
    print(f"\n{'=' * 60}")
    print(f"{tech} TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"{'Distance':<15} {'Congestion':<12} {'DL (kbps)':<12} {'Pass':<6}")
    print("-" * 60)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.distance_scenario:<15} {r.congestion_scenario:<12} "
              f"{r.dl_throughput_kbps:<12.1f} {status:<6}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
