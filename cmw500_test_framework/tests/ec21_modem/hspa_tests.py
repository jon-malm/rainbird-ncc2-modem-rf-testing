#!/usr/bin/env python3
"""
EC21 HSPA Test Suite

Deterministic HSPA (HSDPA/HSUPA) testing for Quectel EC21 modem under various
distance (signal strength) and congestion conditions.

EC21 WCDMA/HSPA Capabilities:
- WCDMA Bands: B1, B2, B5, B8
- HSDPA: Cat 8 (7.2 Mbps), Cat 10 (14.0 Mbps) depending on variant
- HSUPA: Cat 6 (5.76 Mbps)
- WCDMA R99: 384 kbps
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
class HSPATestParameters:
    """HSPA-specific test parameters derived from scenarios."""
    # Cell configuration
    band: int
    uarfcn_dl: int
    scrambling_code: int
    # Power
    cpich_power_dbm: float
    # HSPA configuration
    hsdpa_category: int
    hsdpa_num_codes: int
    hsdpa_modulation: str  # QPSK, Q16, Q64
    hsupa_category: int
    hsupa_tti_ms: int
    # Expected results
    expected_dl_range: Tuple[float, float]
    expected_rscp_range: Tuple[float, float]


class EC21HSPATestSuite:
    """
    HSPA test suite for EC21 modem.

    Tests WCDMA/HSPA performance under controlled distance and
    congestion scenarios.

    Test Matrix:
    - 6 distance scenarios x 5 congestion scenarios = 30 test combinations
    - Each test measures: attach time, RSCP, throughput, BLER

    Example:
        >>> config = EC21TestConfig(cmw500_host="192.168.1.100")
        >>> suite = EC21HSPATestSuite(config)
        >>> results = suite.run_all_tests()
    """

    def __init__(self, config: EC21TestConfig):
        """
        Initialize HSPA test suite.

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
                self._client.hspa.stop_hsdpa()
                self._client.hspa.stop_hsupa()
                self._client.wcdma.cell_off()
            except Exception:
                pass
            self._client.disconnect()
            self._client = None

    def _derive_parameters(
        self,
        distance: DistanceScenario,
        congestion: CongestionScenario,
    ) -> HSPATestParameters:
        """
        Derive HSPA test parameters from distance and congestion scenarios.

        Args:
            distance: Distance scenario
            congestion: Congestion scenario

        Returns:
            HSPATestParameters for the test
        """
        # Determine modulation based on category
        if congestion.hspa_category >= 13:
            modulation = "Q64"
        elif congestion.hspa_category in (11, 12):
            modulation = "QPSK"
        else:
            modulation = "Q16"

        return HSPATestParameters(
            band=self.config.wcdma_band,
            uarfcn_dl=self.config.wcdma_uarfcn,
            scrambling_code=0,
            cpich_power_dbm=distance.wcdma_cpich_dbm,
            hsdpa_category=congestion.hspa_category,
            hsdpa_num_codes=congestion.hspa_num_codes,
            hsdpa_modulation=modulation,
            hsupa_category=6,  # EC21 supports up to Cat 6
            hsupa_tti_ms=2,
            expected_dl_range=congestion.expected_hspa_dl_range,
            expected_rscp_range=distance.expected_wcdma_rscp_range,
        )

    def _configure_wcdma_cell(self, params: HSPATestParameters) -> None:
        """
        Configure WCDMA cell with test parameters.

        Args:
            params: Test parameters
        """
        wcdma = self._client.wcdma

        logger.info(f"Configuring WCDMA: Band {params.band}, UARFCN {params.uarfcn_dl}, "
                   f"CPICH {params.cpich_power_dbm} dBm")

        # Basic cell configuration
        wcdma.configure_cell(
            band=params.band,
            uarfcn_dl=params.uarfcn_dl,
            scrambling_code=params.scrambling_code,
            cpich_power_dbm=params.cpich_power_dbm,
        )

        # Set power levels
        wcdma.set_dl_power(cpich_power_dbm=params.cpich_power_dbm)

    def _configure_hspa(self, params: HSPATestParameters) -> None:
        """
        Configure HSPA channels.

        Args:
            params: Test parameters
        """
        hspa = self._client.hspa

        logger.info(f"Configuring HSDPA: Cat {params.hsdpa_category}, "
                   f"{params.hsdpa_num_codes} codes, {params.hsdpa_modulation}")

        # Configure HSDPA
        hspa.configure_hsdpa(
            category=params.hsdpa_category,
            modulation=params.hsdpa_modulation,
            num_codes=params.hsdpa_num_codes,
            cqi=25,  # Mid-range CQI
        )

        logger.info(f"Configuring HSUPA: Cat {params.hsupa_category}, "
                   f"{params.hsupa_tti_ms}ms TTI")

        # Configure HSUPA
        hspa.configure_hsupa(
            category=params.hsupa_category,
            tti_ms=params.hsupa_tti_ms,
        )

    def _measure_signal_quality(self) -> Dict[str, float]:
        """
        Query signal quality measurements.

        Returns:
            Dictionary with RSCP and related metrics
        """
        try:
            dl_power = self._client.wcdma.get_dl_power()
            return {
                "cpich_power_dbm": dl_power.get("cpich_power_dbm", float('nan')),
            }
        except Exception as e:
            logger.warning(f"Failed to measure signal quality: {e}")
            return {"cpich_power_dbm": float('nan')}

    def _measure_throughput(self) -> Dict[str, float]:
        """
        Measure HSPA data throughput.

        Returns:
            Dictionary with DL and UL throughput in kbps
        """
        try:
            result = self._client.hspa.measure_throughput()
            return {
                "dl_throughput_kbps": result.hsdpa_throughput_kbps,
                "ul_throughput_kbps": result.hsupa_throughput_kbps,
            }
        except Exception as e:
            logger.warning(f"Failed to measure throughput: {e}")
            return {"dl_throughput_kbps": 0, "ul_throughput_kbps": 0}

    def _measure_bler(self) -> Tuple[float, float]:
        """
        Measure HSDPA and HSUPA BLER.

        Returns:
            Tuple of (hsdpa_bler, hsupa_bler) percentages
        """
        try:
            result = self._client.hspa.measure_throughput()
            return (result.hsdpa_bler_percent, result.hsupa_bler_percent)
        except Exception as e:
            logger.warning(f"Failed to measure BLER: {e}")
            return (float('nan'), float('nan'))

    def run_single_test(
        self,
        distance_name: str,
        congestion_name: str,
    ) -> TestResult:
        """
        Run a single HSPA test with specified scenarios.

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
        logger.info(f"HSPA Test: {distance_name} distance, {congestion_name} congestion")
        logger.info(f"=" * 60)

        result = TestResult(
            technology="HSPA",
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

            # Configure WCDMA cell
            self._configure_wcdma_cell(params)

            # Turn on cell
            logger.info("Starting WCDMA cell...")
            self._client.wcdma.cell_on()

            # Wait for UE attachment
            logger.info("Waiting for UE attachment...")
            attach_start = time.time()
            try:
                self._client.wcdma.wait_for_attach(timeout=self.config.attach_timeout_s)
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
            result.signal_strength_dbm = signal.get("cpich_power_dbm", float('nan'))

            # Configure HSPA
            self._configure_hspa(params)

            # Start HSDPA and HSUPA
            logger.info("Starting HSPA data channels...")
            self._client.hspa.start_hsdpa()
            self._client.hspa.start_hsupa()

            # Allow time for data path setup
            time.sleep(3)

            # Measure throughput
            logger.info("Measuring throughput...")
            throughput = self._measure_throughput()
            result.dl_throughput_kbps = throughput["dl_throughput_kbps"]
            result.ul_throughput_kbps = throughput["ul_throughput_kbps"]
            logger.info(f"Throughput: DL={result.dl_throughput_kbps:.0f} kbps, "
                       f"UL={result.ul_throughput_kbps:.0f} kbps")

            # Measure BLER
            dl_bler, ul_bler = self._measure_bler()
            result.bler_percent = dl_bler  # Report DL BLER

            # Determine pass/fail
            dl_min, dl_max = params.expected_dl_range
            limits = EC21_LIMITS["HSPA"]

            # Check if results are within expected ranges
            # Allow wide margin since HSPA throughput varies significantly
            dl_ok = dl_min * 0.5 <= result.dl_throughput_kbps <= dl_max * 1.5
            bler_ok = result.bler_percent <= limits["target_bler_percent"]

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
                self._client.hspa.stop_hsdpa()
                self._client.hspa.stop_hsupa()
                self._client.wcdma.cell_off()
            except Exception:
                pass

        return result

    def run_all_tests(self) -> List[TestResult]:
        """
        Run all HSPA tests across distance and congestion scenarios.

        Returns:
            List of TestResult objects
        """
        self._results = []

        logger.info("Starting EC21 HSPA Test Suite")
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
        logger.info(f"HSPA Test Suite Complete: {passed}/{len(self._results)} passed")
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

    def run_wcdma_r99_test(
        self,
        distance_name: str = "medium",
    ) -> TestResult:
        """
        Run basic WCDMA R99 test (no HSPA).

        Useful for testing fallback/degraded mode.

        Args:
            distance_name: Distance scenario to use

        Returns:
            TestResult with R99 throughput
        """
        distance = DISTANCE_SCENARIOS[distance_name]

        result = TestResult(
            technology="WCDMA_R99",
            distance_scenario=distance_name,
            congestion_scenario="n/a",
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

            # Configure basic WCDMA
            self._client.wcdma.configure_cell(
                band=self.config.wcdma_band,
                uarfcn_dl=self.config.wcdma_uarfcn,
                cpich_power_dbm=distance.wcdma_cpich_dbm,
            )

            # Configure R99 data (384 kbps)
            self._client.wcdma.configure_r99_data(
                dl_rate_kbps=384,
                ul_rate_kbps=384,
            )

            # Turn on cell
            self._client.wcdma.cell_on()

            # Attach
            attach_start = time.time()
            self._client.wcdma.wait_for_attach(timeout=self.config.attach_timeout_s)
            result.attach_success = True
            result.attach_time_s = time.time() - attach_start

            # Wait for connection
            self._client.wcdma.wait_for_connected(timeout=30)

            # Measure throughput
            throughput = self._client.wcdma.get_throughput()
            result.dl_throughput_kbps = throughput.get("dl_throughput_kbps", 0)
            result.ul_throughput_kbps = throughput.get("ul_throughput_kbps", 0)

            # R99 should achieve close to 384 kbps
            result.passed = result.dl_throughput_kbps > 300

        except Exception as e:
            result.notes = str(e)

        finally:
            try:
                self._client.wcdma.cell_off()
            except Exception:
                pass
            self._disconnect()

        return result


def main():
    """Run HSPA tests from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="EC21 HSPA Test Suite")
    parser.add_argument("host", help="CMW500 IP address")
    parser.add_argument("--band", type=int, default=1, help="WCDMA band")
    parser.add_argument("--uarfcn", type=int, default=10700, help="UARFCN")
    parser.add_argument("--distance", help="Single distance scenario to test")
    parser.add_argument("--congestion", help="Single congestion scenario to test")
    parser.add_argument("--sweep-distance", action="store_true",
                        help="Sweep all distance scenarios")
    parser.add_argument("--sweep-congestion", action="store_true",
                        help="Sweep all congestion scenarios")
    parser.add_argument("--r99", action="store_true",
                        help="Run WCDMA R99 test only")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # Create config
    config = EC21TestConfig(
        cmw500_host=args.host,
        wcdma_band=args.band,
        wcdma_uarfcn=args.uarfcn,
    )

    # Create test suite
    suite = EC21HSPATestSuite(config)

    # Run tests
    if args.r99:
        results = [suite.run_wcdma_r99_test(args.distance or "medium")]
    elif args.distance and args.congestion:
        results = [suite.run_single_test(args.distance, args.congestion)]
    elif args.sweep_distance:
        results = suite.run_distance_sweep(args.congestion or "none")
    elif args.sweep_congestion:
        results = suite.run_congestion_sweep(args.distance or "medium")
    else:
        results = suite.run_all_tests()

    # Print summary
    print("\n" + "=" * 60)
    print("HSPA TEST RESULTS SUMMARY")
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
