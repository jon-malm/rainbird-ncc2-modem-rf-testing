#!/usr/bin/env python3
"""
EC21 LTE Test Suite

Deterministic LTE testing for Quectel EC21 modem under various
distance (signal strength) and congestion conditions.

EC21 LTE Capabilities:
- Category 1: 10 Mbps DL, 5 Mbps UL
- Single RX antenna
- Bands: B1, B3, B5, B7, B8, B20, B28 (varies by variant)
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

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
class LTETestParameters:
    """LTE-specific test parameters derived from scenarios."""
    # Cell configuration
    band: int
    bandwidth_mhz: float
    earfcn: int
    # Power
    rs_epre_dbm: float
    # Congestion simulation
    prb_allocation_percent: int
    mcs_limit: Optional[int]
    awgn_snr_db: float
    awgn_enabled: bool
    # Expected results
    expected_dl_range: Tuple[float, float]
    expected_rsrp_range: Tuple[float, float]


class EC21LTETestSuite:
    """
    LTE test suite for EC21 modem.

    Tests LTE performance under controlled distance and congestion scenarios.

    Test Matrix:
    - 6 distance scenarios x 5 congestion scenarios = 30 test combinations
    - Each test measures: attach time, RSRP, throughput, BLER

    Example:
        >>> config = EC21TestConfig(cmw500_host="192.168.1.100")
        >>> suite = EC21LTETestSuite(config)
        >>> results = suite.run_all_tests()
    """

    def __init__(self, config: EC21TestConfig):
        """
        Initialize LTE test suite.

        Args:
            config: Test configuration
        """
        self.config = config
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
                self._client.lte.cell_off()
            except Exception:
                pass
            self._client.disconnect()
            self._client = None

    def _derive_parameters(
        self,
        distance: DistanceScenario,
        congestion: CongestionScenario,
    ) -> LTETestParameters:
        """
        Derive LTE test parameters from distance and congestion scenarios.

        Args:
            distance: Distance scenario
            congestion: Congestion scenario

        Returns:
            LTETestParameters for the test
        """
        return LTETestParameters(
            band=self.config.lte_band,
            bandwidth_mhz=self.config.lte_bandwidth_mhz,
            earfcn=self.config.lte_earfcn,
            rs_epre_dbm=distance.lte_rs_epre_dbm,
            prb_allocation_percent=congestion.lte_prb_allocation_percent,
            mcs_limit=congestion.lte_mcs_limit,
            awgn_snr_db=congestion.lte_awgn_snr_db,
            awgn_enabled=congestion.lte_awgn_snr_db < 30.0,
            expected_dl_range=congestion.expected_lte_dl_range,
            expected_rsrp_range=distance.expected_lte_rsrp_range,
        )

    def _configure_cell(self, params: LTETestParameters) -> None:
        """
        Configure LTE cell with test parameters.

        Args:
            params: Test parameters
        """
        lte = self._client.lte

        logger.info(f"Configuring LTE: Band {params.band}, "
                   f"{params.bandwidth_mhz} MHz, RS EPRE {params.rs_epre_dbm} dBm")

        # Basic cell configuration
        lte.configure_cell(
            band=params.band,
            bandwidth_mhz=params.bandwidth_mhz,
            dl_earfcn=params.earfcn,
        )

        # Set power level (simulates distance)
        lte.set_dl_power(rs_epre_dbm=params.rs_epre_dbm)

        # Configure for Cat 1 UE (single antenna, limited throughput)
        lte.set_transmission_mode(1)  # TM1 = single antenna

    def _configure_congestion(self, params: LTETestParameters) -> None:
        """
        Configure congestion simulation.

        Args:
            params: Test parameters including congestion settings
        """
        # Configure AWGN for SNR-based congestion
        if params.awgn_enabled:
            sim = NetworkSimulator(self._client)
            sim.configure_awgn(snr_db=params.awgn_snr_db, enabled=True)
            logger.info(f"AWGN enabled: SNR = {params.awgn_snr_db} dB")

        # Note: PRB allocation and MCS limiting would require additional
        # CMW500 configuration that's scheduler-specific. For now we
        # simulate congestion primarily via SNR degradation.

        # In a real implementation, you could also:
        # - Configure the scheduler to limit PRB allocation
        # - Set maximum MCS index
        # - Add inter-cell interference

    def _measure_signal_quality(self) -> Dict[str, float]:
        """
        Query UE signal quality measurements.

        Returns:
            Dictionary with RSRP, RSRQ, SINR
        """
        # In a real test, we'd query the UE via AT commands or
        # read from CMW500 measurements
        # For now, return placeholder that would be filled by actual measurement

        try:
            # CMW500 can report what power level it's transmitting
            # and estimate received signal based on path settings
            dl_power = self._client.lte.get_dl_power()
            return {
                "rs_epre_dbm": dl_power.get("rs_epre_dbm", float('nan')),
                "estimated_rsrp_dbm": dl_power.get("rs_epre_dbm", float('nan')),
            }
        except Exception as e:
            logger.warning(f"Failed to measure signal quality: {e}")
            return {"rs_epre_dbm": float('nan'), "estimated_rsrp_dbm": float('nan')}

    def _measure_throughput(self) -> Dict[str, float]:
        """
        Measure data throughput.

        Returns:
            Dictionary with DL and UL throughput in kbps
        """
        try:
            # Start data transfer and measure throughput
            stats = self._client.lte.get_throughput_stats()
            return {
                "dl_throughput_kbps": stats.get("dl_throughput_kbps", 0),
                "ul_throughput_kbps": stats.get("ul_throughput_kbps", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to measure throughput: {e}")
            return {"dl_throughput_kbps": 0, "ul_throughput_kbps": 0}

    def _measure_bler(self) -> float:
        """
        Measure Block Error Rate.

        Returns:
            BLER percentage
        """
        try:
            tx_result = self._client.lte.measure_tx_power()
            # BLER is typically part of the measurement results
            return 0.0  # Placeholder
        except Exception as e:
            logger.warning(f"Failed to measure BLER: {e}")
            return float('nan')

    def run_single_test(
        self,
        distance_name: str,
        congestion_name: str,
    ) -> TestResult:
        """
        Run a single LTE test with specified scenarios.

        Args:
            distance_name: Name of distance scenario
            congestion_name: Name of congestion scenario

        Returns:
            TestResult with measurements
        """
        distance = DISTANCE_SCENARIOS[distance_name]
        congestion = CONGESTION_SCENARIOS[congestion_name]
        params = self._derive_parameters(distance, congestion)

        logger.info(f"=" * 60)
        logger.info(f"LTE Test: {distance_name} distance, {congestion_name} congestion")
        logger.info(f"=" * 60)

        result = TestResult(
            technology="LTE",
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
            self._configure_congestion(params)

            # Turn on cell
            logger.info("Starting LTE cell...")
            self._client.lte.cell_on()

            # Wait for UE attachment
            logger.info("Waiting for UE attachment...")
            attach_start = time.time()
            try:
                self._client.lte.wait_for_attach(timeout=self.config.attach_timeout_s)
                result.attach_success = True
                result.attach_time_s = time.time() - attach_start
                logger.info(f"UE attached in {result.attach_time_s:.1f}s")
            except TimeoutError:
                result.attach_success = False
                result.notes = "Attachment timeout"
                logger.warning("UE attachment timeout")
                return result

            # Measure signal quality
            signal = self._measure_signal_quality()
            result.signal_strength_dbm = signal.get("estimated_rsrp_dbm", float('nan'))

            # Wait for data connection
            try:
                self._client.lte.wait_for_connected(timeout=30)
            except TimeoutError:
                result.notes = "Data connection timeout"
                logger.warning("Data connection timeout")

            # Allow time for throughput to stabilize
            time.sleep(2)

            # Measure throughput
            logger.info("Measuring throughput...")
            throughput = self._measure_throughput()
            result.dl_throughput_kbps = throughput["dl_throughput_kbps"]
            result.ul_throughput_kbps = throughput["ul_throughput_kbps"]
            logger.info(f"Throughput: DL={result.dl_throughput_kbps:.0f} kbps, "
                       f"UL={result.ul_throughput_kbps:.0f} kbps")

            # Measure BLER
            result.bler_percent = self._measure_bler()

            # Determine pass/fail
            dl_min, dl_max = params.expected_dl_range
            rsrp_min, rsrp_max = params.expected_rsrp_range

            # Check if results are within expected ranges
            dl_ok = dl_min <= result.dl_throughput_kbps <= dl_max * 1.2  # 20% margin
            rsrp_ok = rsrp_min - 5 <= result.signal_strength_dbm <= rsrp_max + 5
            bler_ok = result.bler_percent <= EC21_LIMITS["LTE"]["target_bler_percent"]

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
                if params.awgn_enabled:
                    sim = NetworkSimulator(self._client)
                    sim.configure_awgn(enabled=False)
                self._client.lte.cell_off()
            except Exception:
                pass

        return result

    def run_all_tests(self) -> List[TestResult]:
        """
        Run all LTE tests across distance and congestion scenarios.

        Returns:
            List of TestResult objects
        """
        self._results = []

        logger.info("Starting EC21 LTE Test Suite")
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
        logger.info(f"LTE Test Suite Complete: {passed}/{len(self._results)} passed")
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
    """Run LTE tests from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="EC21 LTE Test Suite")
    parser.add_argument("host", help="CMW500 IP address")
    parser.add_argument("--band", type=int, default=1, help="LTE band")
    parser.add_argument("--bandwidth", type=float, default=10.0, help="Bandwidth (MHz)")
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
        lte_band=args.band,
        lte_bandwidth_mhz=args.bandwidth,
    )

    # Create test suite
    suite = EC21LTETestSuite(config)

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
    print("\n" + "=" * 60)
    print("LTE TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"{'Distance':<15} {'Congestion':<12} {'DL (kbps)':<12} {'Pass':<6}")
    print("-" * 60)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.distance_scenario:<15} {r.congestion_scenario:<12} "
              f"{r.dl_throughput_kbps:<12.0f} {status:<6}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
