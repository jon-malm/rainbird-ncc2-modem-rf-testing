"""
EC21 Modem Unified Test Runner

Coordinates running all technology tests (LTE, GPRS, HSPA) for the Quectel EC21 modem
under controlled distance and congestion scenarios, including carrier failover testing.

Usage:
    # Run all tests with defaults
    python -m cmw500_test_framework.tests.ec21_modem.test_runner

    # Run specific technology
    python -m cmw500_test_framework.tests.ec21_modem.test_runner --technology LTE

    # Run specific scenarios
    python -m cmw500_test_framework.tests.ec21_modem.test_runner --distance medium,far --congestion none,moderate

    # Run carrier failover tests
    python -m cmw500_test_framework.tests.ec21_modem.test_runner --mode failover

    # Run failover between specific carriers
    python -m cmw500_test_framework.tests.ec21_modem.test_runner --mode failover --carriers att,tmobile

    # Use config file
    python -m cmw500_test_framework.tests.ec21_modem.test_runner --config ec21_config.yaml
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .test_config import (
    EC21TestConfig,
    TestResult,
    TestSuiteResult,
    DISTANCE_SCENARIOS,
    CONGESTION_SCENARIOS,
    EC21_LIMITS,
    Technology,
)
from .lte_tests import EC21LTETestSuite
from .gprs_tests import EC21GPRSTestSuite
from .hspa_tests import EC21HSPATestSuite
from .carrier_config import (
    CARRIER_CONFIGS,
    FAILOVER_SCENARIOS,
    FailoverTestResult,
    get_carrier_config,
    get_all_carriers,
)
from .failover_tests import EC21FailoverTestSuite

# Import CMW500 client
from ...core.client import CMW500Client

logger = logging.getLogger(__name__)


class EC21TestRunner:
    """
    Unified test runner for EC21 modem deterministic testing.

    Coordinates running all technology tests under controlled
    distance and congestion scenarios.
    """

    def __init__(self, config: EC21TestConfig = None, ec21_variant: str = "A"):
        """
        Initialize test runner.

        Args:
            config: Test configuration (uses defaults if not provided)
            ec21_variant: EC21 variant (A, V, AUT) - affects carrier band support
        """
        self.config = config or EC21TestConfig()
        self.client: Optional[CMW500Client] = None
        self.ec21_variant = ec21_variant

        # Test suites (lazy initialization)
        self._lte_suite: Optional[EC21LTETestSuite] = None
        self._gprs_suite: Optional[EC21GPRSTestSuite] = None
        self._hspa_suite: Optional[EC21HSPATestSuite] = None
        self._failover_suite: Optional[EC21FailoverTestSuite] = None

        # Results storage
        self.results: List[TestResult] = []
        self.failover_results: List[FailoverTestResult] = []
        self.suite_result: Optional[TestSuiteResult] = None

        # Setup logging
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging for test runner."""
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
            ]
        )

        # Create output directory if needed
        if self.config.output_dir:
            os.makedirs(self.config.output_dir, exist_ok=True)
            # Add file handler
            log_file = os.path.join(
                self.config.output_dir,
                f"ec21_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)

    def connect(self) -> bool:
        """
        Connect to CMW500.

        Returns:
            True if connection successful
        """
        try:
            logger.info(f"Connecting to CMW500 at {self.config.cmw500_host}...")
            self.client = CMW500Client(
                host=self.config.cmw500_host,
                port=self.config.cmw500_port,
                timeout=self.config.cmw500_timeout,
            )
            self.client.connect()

            info = self.client.get_system_info()
            logger.info(f"Connected to {info.model} (S/N: {info.serial_number})")
            logger.info(f"Firmware: {info.firmware_version}")

            return True

        except Exception as e:
            logger.error(f"Failed to connect to CMW500: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from CMW500."""
        if self.client:
            logger.info("Disconnecting from CMW500...")
            self.client.disconnect()
            self.client = None

    @property
    def lte_suite(self) -> EC21LTETestSuite:
        """Get LTE test suite instance."""
        if self._lte_suite is None:
            self._lte_suite = EC21LTETestSuite(self.client, self.config)
        return self._lte_suite

    @property
    def gprs_suite(self) -> EC21GPRSTestSuite:
        """Get GPRS test suite instance."""
        if self._gprs_suite is None:
            self._gprs_suite = EC21GPRSTestSuite(self.client, self.config)
        return self._gprs_suite

    @property
    def hspa_suite(self) -> EC21HSPATestSuite:
        """Get HSPA test suite instance."""
        if self._hspa_suite is None:
            self._hspa_suite = EC21HSPATestSuite(self.client, self.config)
        return self._hspa_suite

    @property
    def failover_suite(self) -> EC21FailoverTestSuite:
        """Get failover test suite instance."""
        if self._failover_suite is None:
            self._failover_suite = EC21FailoverTestSuite(
                self.client, self.config, self.ec21_variant
            )
        return self._failover_suite

    def _get_test_matrix(self) -> List[Tuple[str, str, str]]:
        """
        Generate test matrix of (technology, distance, congestion) combinations.

        Returns:
            List of (technology, distance_scenario, congestion_scenario) tuples
        """
        matrix = []

        for tech in self.config.technologies:
            tech_upper = tech.upper()
            for distance in self.config.distance_scenarios:
                for congestion in self.config.congestion_scenarios:
                    matrix.append((tech_upper, distance, congestion))

        return matrix

    def run_single_test(
        self,
        technology: str,
        distance_scenario: str,
        congestion_scenario: str,
    ) -> Optional[TestResult]:
        """
        Run a single test with specified parameters.

        Args:
            technology: Technology to test (LTE, HSPA, GPRS)
            distance_scenario: Distance scenario name
            congestion_scenario: Congestion scenario name

        Returns:
            TestResult or None if test failed to execute
        """
        logger.info(f"Running test: {technology} / {distance_scenario} / {congestion_scenario}")

        try:
            if technology == "LTE":
                return self.lte_suite.run_single_test(
                    distance_scenario,
                    congestion_scenario,
                )
            elif technology == "HSPA":
                return self.hspa_suite.run_single_test(
                    distance_scenario,
                    congestion_scenario,
                )
            elif technology in ("GPRS", "EDGE"):
                return self.gprs_suite.run_single_test(
                    distance_scenario,
                    congestion_scenario,
                    use_edge=(technology == "EDGE"),
                )
            else:
                logger.error(f"Unknown technology: {technology}")
                return None

        except Exception as e:
            logger.error(f"Test execution error: {e}")
            return None

    def run_technology_tests(
        self,
        technology: str,
        distance_scenarios: List[str] = None,
        congestion_scenarios: List[str] = None,
    ) -> List[TestResult]:
        """
        Run all tests for a specific technology.

        Args:
            technology: Technology to test
            distance_scenarios: Distance scenarios to test (None = all)
            congestion_scenarios: Congestion scenarios to test (None = all)

        Returns:
            List of TestResult objects
        """
        distances = distance_scenarios or self.config.distance_scenarios
        congestions = congestion_scenarios or self.config.congestion_scenarios

        results = []
        total = len(distances) * len(congestions)
        current = 0

        logger.info(f"Running {total} {technology} tests...")

        for distance in distances:
            for congestion in congestions:
                current += 1
                logger.info(f"Test {current}/{total}: {distance} / {congestion}")

                result = self.run_single_test(technology, distance, congestion)
                if result:
                    results.append(result)
                    self.results.append(result)

                # Brief pause between tests
                time.sleep(1)

        return results

    def run_distance_sweep(
        self,
        technology: str,
        congestion: str = "none",
    ) -> List[TestResult]:
        """
        Run distance sweep for a technology at fixed congestion.

        Args:
            technology: Technology to test
            congestion: Congestion scenario (default: none)

        Returns:
            List of TestResult objects
        """
        logger.info(f"Running {technology} distance sweep (congestion={congestion})...")

        if technology == "LTE":
            return self.lte_suite.run_distance_sweep(congestion)
        elif technology == "HSPA":
            return self.hspa_suite.run_distance_sweep(congestion)
        elif technology in ("GPRS", "EDGE"):
            return self.gprs_suite.run_distance_sweep(
                congestion,
                use_edge=(technology == "EDGE")
            )
        else:
            logger.error(f"Unknown technology: {technology}")
            return []

    def run_congestion_sweep(
        self,
        technology: str,
        distance: str = "medium",
    ) -> List[TestResult]:
        """
        Run congestion sweep for a technology at fixed distance.

        Args:
            technology: Technology to test
            distance: Distance scenario (default: medium)

        Returns:
            List of TestResult objects
        """
        logger.info(f"Running {technology} congestion sweep (distance={distance})...")

        if technology == "LTE":
            return self.lte_suite.run_congestion_sweep(distance)
        elif technology == "HSPA":
            return self.hspa_suite.run_congestion_sweep(distance)
        elif technology in ("GPRS", "EDGE"):
            return self.gprs_suite.run_congestion_sweep(
                distance,
                use_edge=(technology == "EDGE")
            )
        else:
            logger.error(f"Unknown technology: {technology}")
            return []

    def run_all_tests(self) -> TestSuiteResult:
        """
        Run complete test suite across all technologies and scenarios.

        Returns:
            TestSuiteResult with all test results
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("EC21 MODEM DETERMINISTIC TEST SUITE")
        logger.info("=" * 60)
        logger.info(f"Start time: {start_time.isoformat()}")
        logger.info(f"Technologies: {self.config.technologies}")
        logger.info(f"Distance scenarios: {self.config.distance_scenarios}")
        logger.info(f"Congestion scenarios: {self.config.congestion_scenarios}")

        test_matrix = self._get_test_matrix()
        total_tests = len(test_matrix)
        logger.info(f"Total tests to run: {total_tests}")
        logger.info("=" * 60)

        self.results = []

        for idx, (tech, distance, congestion) in enumerate(test_matrix, 1):
            logger.info(f"\n[{idx}/{total_tests}] {tech} | {distance} | {congestion}")
            logger.info("-" * 40)

            result = self.run_single_test(tech, distance, congestion)
            if result:
                self.results.append(result)
                status = "PASS" if result.passed else "FAIL"
                logger.info(f"Result: {status}")
                logger.info(f"  DL: {result.dl_throughput_kbps:.1f} kbps")
                logger.info(f"  UL: {result.ul_throughput_kbps:.1f} kbps")
                logger.info(f"  Signal: {result.signal_strength_dbm:.1f} dBm")

            # Pause between tests for stability
            time.sleep(2)

        end_time = datetime.now()

        # Calculate summary
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        self.suite_result = TestSuiteResult(
            config=self.config,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            results=self.results,
            total_tests=len(self.results),
            passed_tests=passed,
            failed_tests=failed,
        )

        logger.info("\n" + "=" * 60)
        logger.info("TEST SUITE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Duration: {end_time - start_time}")
        logger.info(f"Total tests: {self.suite_result.total_tests}")
        logger.info(f"Passed: {self.suite_result.passed_tests}")
        logger.info(f"Failed: {self.suite_result.failed_tests}")
        logger.info(f"Pass rate: {self.suite_result.pass_rate:.1f}%")

        # Generate report if configured
        if self.config.generate_report:
            self.generate_report()

        return self.suite_result

    def run_failover_tests(
        self,
        carriers: List[str] = None,
        scenarios: List[str] = None,
    ) -> List[FailoverTestResult]:
        """
        Run carrier failover tests.

        Args:
            carriers: List of carriers to test (default: all - att, tmobile, verizon)
            scenarios: Specific scenario names to run (default: all)

        Returns:
            List of FailoverTestResult objects
        """
        logger.info("=" * 60)
        logger.info("EC21 CARRIER FAILOVER TEST SUITE")
        logger.info("=" * 60)
        logger.info(f"EC21 Variant: {self.ec21_variant}")

        if scenarios:
            # Run specific scenarios
            results = []
            for scenario_name in scenarios:
                if scenario_name in FAILOVER_SCENARIOS:
                    scenario = FAILOVER_SCENARIOS[scenario_name]
                    result = self.failover_suite.run_failover_test(scenario)
                    if result:
                        results.append(result)
                        self.failover_results.append(result)
                else:
                    logger.warning(f"Unknown scenario: {scenario_name}")
            return results

        if carriers:
            # Run failover between specified carriers
            results = []
            carrier_list = [c.lower() for c in carriers]

            # Generate carrier pairs
            for i, primary in enumerate(carrier_list):
                for secondary in carrier_list[i+1:]:
                    logger.info(f"Testing failover: {primary} -> {secondary}")
                    result = self.failover_suite.run_carrier_pair_test(primary, secondary)
                    if result:
                        results.append(result)
                        self.failover_results.append(result)

                    # Also test reverse direction
                    logger.info(f"Testing failover: {secondary} -> {primary}")
                    result = self.failover_suite.run_carrier_pair_test(secondary, primary)
                    if result:
                        results.append(result)
                        self.failover_results.append(result)

            return results

        # Run all failover tests
        return self.failover_suite.run_all_failover_tests()

    def run_triple_failover(self) -> Optional[FailoverTestResult]:
        """
        Run triple failover test (AT&T -> T-Mobile -> Verizon).

        Returns:
            FailoverTestResult or None
        """
        return self.failover_suite.run_triple_failover_test()

    def generate_failover_report(self, output_path: str = None) -> str:
        """
        Generate failover test report.

        Args:
            output_path: Output file path (auto-generated if not specified)

        Returns:
            Path to generated report
        """
        if not self.failover_results:
            logger.warning("No failover test results to report")
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_path = output_path or os.path.join(
            self.config.output_dir,
            f"ec21_failover_report_{timestamp}.json"
        )

        # Get summary from failover suite
        summary = self.failover_suite.get_results_summary()

        report_data = {
            "summary": {
                "total_tests": summary["total"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "pass_rate_percent": summary.get("pass_rate_percent", 0),
            },
            "ec21_variant": self.ec21_variant,
            "by_carrier_pair": summary.get("by_carrier_pair", {}),
            "results": [asdict(r) for r in self.failover_results],
        }

        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        logger.info(f"Failover report saved to: {json_path}")

        # Generate text summary
        txt_path = json_path.replace('.json', '.txt')
        self._generate_failover_text_report(txt_path)

        return json_path

    def _generate_failover_text_report(self, path: str) -> None:
        """Generate text format failover report."""
        with open(path, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("QUECTEL EC21 CARRIER FAILOVER TEST REPORT\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"EC21 Variant: {self.ec21_variant}\n")
            f.write(f"Total Tests: {len(self.failover_results)}\n")

            passed = sum(1 for r in self.failover_results if r.passed)
            f.write(f"Passed: {passed}\n")
            f.write(f"Failed: {len(self.failover_results) - passed}\n")
            f.write(f"Pass Rate: {(passed/len(self.failover_results)*100) if self.failover_results else 0:.1f}%\n\n")

            # Results by carrier pair
            f.write("RESULTS BY CARRIER PAIR\n")
            f.write("-" * 40 + "\n")

            carrier_pairs = {}
            for r in self.failover_results:
                pair = f"{r.primary_carrier} -> {r.final_carrier or 'N/A'}"
                if pair not in carrier_pairs:
                    carrier_pairs[pair] = {"results": [], "times": []}
                carrier_pairs[pair]["results"].append(r)
                if r.failover_successful:
                    carrier_pairs[pair]["times"].append(r.failover_time_s)

            for pair, data in carrier_pairs.items():
                passed = sum(1 for r in data["results"] if r.passed)
                avg_time = sum(data["times"]) / len(data["times"]) if data["times"] else 0
                f.write(f"\n{pair}:\n")
                f.write(f"  Tests: {len(data['results'])} (Pass: {passed})\n")
                f.write(f"  Avg Failover Time: {avg_time:.2f}s\n")

            # Detailed results
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("DETAILED RESULTS\n")
            f.write("=" * 70 + "\n")

            for r in self.failover_results:
                status = "PASS" if r.passed else "FAIL"
                f.write(f"\n[{status}] {r.scenario_name}\n")
                f.write(f"  Timestamp: {r.timestamp}\n")
                f.write(f"  Primary: {r.primary_carrier} ({r.primary_technology} Band {r.primary_band})\n")
                f.write(f"  Primary Signal: {r.primary_rsrp_dbm:.1f} dBm\n")
                f.write(f"  Failover Triggered: {r.failover_triggered}\n")
                f.write(f"  Failover Successful: {r.failover_successful}\n")
                f.write(f"  Failover Time: {r.failover_time_s:.2f}s\n")
                if r.failover_successful:
                    f.write(f"  Final: {r.final_carrier} ({r.final_technology} Band {r.final_band})\n")
                    f.write(f"  Final Signal: {r.final_rsrp_dbm:.1f} dBm\n")
                if r.failure_reason:
                    f.write(f"  Failure Reason: {r.failure_reason}\n")

        logger.info(f"Failover text report saved to: {path}")

    def generate_report(self, output_path: str = None) -> str:
        """
        Generate comprehensive test report.

        Args:
            output_path: Output file path (auto-generated if not specified)

        Returns:
            Path to generated report
        """
        if not self.suite_result:
            logger.warning("No test results to report")
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Generate JSON report
        json_path = output_path or os.path.join(
            self.config.output_dir,
            f"ec21_test_report_{timestamp}.json"
        )

        report_data = {
            "summary": {
                "start_time": self.suite_result.start_time,
                "end_time": self.suite_result.end_time,
                "total_tests": self.suite_result.total_tests,
                "passed_tests": self.suite_result.passed_tests,
                "failed_tests": self.suite_result.failed_tests,
                "pass_rate_percent": self.suite_result.pass_rate,
            },
            "config": asdict(self.config),
            "results": [asdict(r) for r in self.suite_result.results],
            "results_by_technology": self._group_results_by_technology(),
            "results_by_distance": self._group_results_by_distance(),
            "results_by_congestion": self._group_results_by_congestion(),
        }

        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        logger.info(f"JSON report saved to: {json_path}")

        # Generate CSV summary
        csv_path = json_path.replace('.json', '.csv')
        self._generate_csv_report(csv_path)
        logger.info(f"CSV report saved to: {csv_path}")

        # Generate text summary
        txt_path = json_path.replace('.json', '.txt')
        self._generate_text_report(txt_path)
        logger.info(f"Text report saved to: {txt_path}")

        return json_path

    def _group_results_by_technology(self) -> Dict[str, Dict[str, Any]]:
        """Group results by technology with statistics."""
        grouped = {}

        for tech in self.config.technologies:
            tech_results = [r for r in self.results if r.technology == tech]
            if tech_results:
                passed = sum(1 for r in tech_results if r.passed)
                grouped[tech] = {
                    "total": len(tech_results),
                    "passed": passed,
                    "failed": len(tech_results) - passed,
                    "pass_rate_percent": (passed / len(tech_results)) * 100,
                    "avg_dl_throughput_kbps": sum(r.dl_throughput_kbps for r in tech_results) / len(tech_results),
                    "avg_ul_throughput_kbps": sum(r.ul_throughput_kbps for r in tech_results) / len(tech_results),
                    "avg_signal_strength_dbm": sum(r.signal_strength_dbm for r in tech_results) / len(tech_results),
                }

        return grouped

    def _group_results_by_distance(self) -> Dict[str, Dict[str, Any]]:
        """Group results by distance scenario with statistics."""
        grouped = {}

        for distance in self.config.distance_scenarios:
            dist_results = [r for r in self.results if r.distance_scenario == distance]
            if dist_results:
                passed = sum(1 for r in dist_results if r.passed)
                grouped[distance] = {
                    "total": len(dist_results),
                    "passed": passed,
                    "failed": len(dist_results) - passed,
                    "pass_rate_percent": (passed / len(dist_results)) * 100,
                    "avg_dl_throughput_kbps": sum(r.dl_throughput_kbps for r in dist_results) / len(dist_results),
                    "avg_signal_strength_dbm": sum(r.signal_strength_dbm for r in dist_results) / len(dist_results),
                }

        return grouped

    def _group_results_by_congestion(self) -> Dict[str, Dict[str, Any]]:
        """Group results by congestion scenario with statistics."""
        grouped = {}

        for congestion in self.config.congestion_scenarios:
            cong_results = [r for r in self.results if r.congestion_scenario == congestion]
            if cong_results:
                passed = sum(1 for r in cong_results if r.passed)
                grouped[congestion] = {
                    "total": len(cong_results),
                    "passed": passed,
                    "failed": len(cong_results) - passed,
                    "pass_rate_percent": (passed / len(cong_results)) * 100,
                    "avg_dl_throughput_kbps": sum(r.dl_throughput_kbps for r in cong_results) / len(cong_results),
                }

        return grouped

    def _generate_csv_report(self, path: str) -> None:
        """Generate CSV format report."""
        import csv

        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                "Technology",
                "Distance",
                "Congestion",
                "Attach Success",
                "Attach Time (s)",
                "Signal (dBm)",
                "Quality",
                "DL (kbps)",
                "UL (kbps)",
                "BLER (%)",
                "Pass/Fail",
                "Notes",
            ])

            # Data rows
            for r in self.results:
                writer.writerow([
                    r.technology,
                    r.distance_scenario,
                    r.congestion_scenario,
                    r.attach_success,
                    f"{r.attach_time_s:.2f}",
                    f"{r.signal_strength_dbm:.1f}",
                    f"{r.signal_quality:.2f}",
                    f"{r.dl_throughput_kbps:.1f}",
                    f"{r.ul_throughput_kbps:.1f}",
                    f"{r.bler_percent:.2f}",
                    "PASS" if r.passed else "FAIL",
                    r.notes,
                ])

    def _generate_text_report(self, path: str) -> None:
        """Generate text format report."""
        with open(path, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("QUECTEL EC21 MODEM DETERMINISTIC TEST REPORT\n")
            f.write("=" * 70 + "\n\n")

            # Summary
            f.write("TEST SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Start Time:   {self.suite_result.start_time}\n")
            f.write(f"End Time:     {self.suite_result.end_time}\n")
            f.write(f"Total Tests:  {self.suite_result.total_tests}\n")
            f.write(f"Passed:       {self.suite_result.passed_tests}\n")
            f.write(f"Failed:       {self.suite_result.failed_tests}\n")
            f.write(f"Pass Rate:    {self.suite_result.pass_rate:.1f}%\n\n")

            # Results by technology
            f.write("RESULTS BY TECHNOLOGY\n")
            f.write("-" * 40 + "\n")
            for tech, stats in self._group_results_by_technology().items():
                f.write(f"\n{tech}:\n")
                f.write(f"  Tests: {stats['total']} (Pass: {stats['passed']}, Fail: {stats['failed']})\n")
                f.write(f"  Pass Rate: {stats['pass_rate_percent']:.1f}%\n")
                f.write(f"  Avg DL: {stats['avg_dl_throughput_kbps']:.1f} kbps\n")
                f.write(f"  Avg UL: {stats['avg_ul_throughput_kbps']:.1f} kbps\n")
                f.write(f"  Avg Signal: {stats['avg_signal_strength_dbm']:.1f} dBm\n")

            # Results by distance
            f.write("\n\nRESULTS BY DISTANCE\n")
            f.write("-" * 40 + "\n")
            for dist, stats in self._group_results_by_distance().items():
                scenario = DISTANCE_SCENARIOS.get(dist)
                dist_km = scenario.distance_km if scenario else "?"
                f.write(f"\n{dist} ({dist_km} km):\n")
                f.write(f"  Pass Rate: {stats['pass_rate_percent']:.1f}%\n")
                f.write(f"  Avg DL: {stats['avg_dl_throughput_kbps']:.1f} kbps\n")
                f.write(f"  Avg Signal: {stats['avg_signal_strength_dbm']:.1f} dBm\n")

            # Results by congestion
            f.write("\n\nRESULTS BY CONGESTION\n")
            f.write("-" * 40 + "\n")
            for cong, stats in self._group_results_by_congestion().items():
                f.write(f"\n{cong}:\n")
                f.write(f"  Pass Rate: {stats['pass_rate_percent']:.1f}%\n")
                f.write(f"  Avg DL: {stats['avg_dl_throughput_kbps']:.1f} kbps\n")

            # Detailed results
            f.write("\n\n" + "=" * 70 + "\n")
            f.write("DETAILED RESULTS\n")
            f.write("=" * 70 + "\n")

            for r in self.results:
                status = "PASS" if r.passed else "FAIL"
                f.write(f"\n[{status}] {r.technology} | {r.distance_scenario} | {r.congestion_scenario}\n")
                f.write(f"  Timestamp: {r.timestamp}\n")
                f.write(f"  Attach: {'OK' if r.attach_success else 'FAIL'} ({r.attach_time_s:.2f}s)\n")
                f.write(f"  Signal: {r.signal_strength_dbm:.1f} dBm (Quality: {r.signal_quality:.2f})\n")
                f.write(f"  Throughput: DL={r.dl_throughput_kbps:.1f} kbps, UL={r.ul_throughput_kbps:.1f} kbps\n")
                f.write(f"  BLER: {r.bler_percent:.2f}%\n")
                if r.notes:
                    f.write(f"  Notes: {r.notes}\n")

    @classmethod
    def from_config_file(cls, path: str) -> "EC21TestRunner":
        """
        Create test runner from YAML configuration file.

        Args:
            path: Path to YAML config file

        Returns:
            EC21TestRunner instance
        """
        with open(path, 'r') as f:
            config_dict = yaml.safe_load(f)

        config = EC21TestConfig(**config_dict)
        return cls(config)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="EC21 Modem Deterministic Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests with defaults
  %(prog)s --host 192.168.1.100

  # Run only LTE tests
  %(prog)s --host 192.168.1.100 --technology LTE

  # Run specific distance scenarios
  %(prog)s --host 192.168.1.100 --distance close,medium,far

  # Run distance sweep (all distances, no congestion)
  %(prog)s --host 192.168.1.100 --mode distance_sweep --technology LTE

  # Run carrier failover tests (all carriers)
  %(prog)s --host 192.168.1.100 --mode failover

  # Run failover between specific carriers
  %(prog)s --host 192.168.1.100 --mode failover --carriers att,tmobile

  # Run triple failover test (AT&T -> T-Mobile -> Verizon)
  %(prog)s --host 192.168.1.100 --mode triple_failover

  # Run with Verizon-optimized EC21-V variant
  %(prog)s --host 192.168.1.100 --mode failover --ec21-variant V

  # Use config file
  %(prog)s --config test_config.yaml
        """
    )

    # Connection
    parser.add_argument(
        "--host",
        type=str,
        default="192.168.1.100",
        help="CMW500 IP address (default: 192.168.1.100)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5025,
        help="CMW500 SCPI port (default: 5025)"
    )

    # Configuration
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to YAML configuration file"
    )

    # Test selection
    parser.add_argument(
        "--technology", "-t",
        type=str,
        help="Technologies to test (comma-separated: LTE,HSPA,GPRS,EDGE)"
    )
    parser.add_argument(
        "--distance", "-d",
        type=str,
        help="Distance scenarios (comma-separated: very_close,close,medium,far,very_far,cell_edge)"
    )
    parser.add_argument(
        "--congestion", "-g",
        type=str,
        help="Congestion scenarios (comma-separated: none,light,moderate,heavy,extreme)"
    )

    # Test mode
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["full", "distance_sweep", "congestion_sweep", "single", "failover", "triple_failover"],
        default="full",
        help="Test mode (default: full). Use 'failover' for carrier failover tests."
    )

    # Failover-specific options
    parser.add_argument(
        "--carriers",
        type=str,
        help="Carriers for failover testing (comma-separated: att,tmobile,verizon)"
    )
    parser.add_argument(
        "--failover-scenarios",
        type=str,
        help="Specific failover scenarios to run (comma-separated)"
    )
    parser.add_argument(
        "--ec21-variant",
        type=str,
        default="A",
        choices=["A", "V", "AUT"],
        help="EC21 variant for carrier band compatibility (default: A)"
    )

    # Output
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="./test_results",
        help="Output directory for reports (default: ./test_results)"
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Disable report generation"
    )

    # Verbosity
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-essential output"
    )

    # Dry run
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be run without executing"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    # Create configuration
    if args.config:
        runner = EC21TestRunner.from_config_file(args.config)
    else:
        config = EC21TestConfig(
            cmw500_host=args.host,
            cmw500_port=args.port,
            output_dir=args.output,
            generate_report=not args.no_report,
        )

        # Parse technology selection
        if args.technology:
            config.technologies = [t.strip().upper() for t in args.technology.split(",")]

        # Parse distance scenarios
        if args.distance:
            config.distance_scenarios = [d.strip() for d in args.distance.split(",")]

        # Parse congestion scenarios
        if args.congestion:
            config.congestion_scenarios = [c.strip() for c in args.congestion.split(",")]

        runner = EC21TestRunner(config, ec21_variant=args.ec21_variant)

    # Dry run - just show configuration
    if args.dry_run:
        print("\nDRY RUN - Test Configuration:")
        print("-" * 40)
        print(f"CMW500 Host: {runner.config.cmw500_host}")
        print(f"Test mode: {args.mode}")
        print(f"EC21 Variant: {runner.ec21_variant}")

        if args.mode in ("failover", "triple_failover"):
            print("\nCarrier Failover Mode")
            if args.carriers:
                carriers = [c.strip() for c in args.carriers.split(",")]
                print(f"Carriers: {carriers}")
            else:
                print("Carriers: AT&T, T-Mobile, Verizon (all)")

            if args.failover_scenarios:
                scenarios = [s.strip() for s in args.failover_scenarios.split(",")]
                print(f"Scenarios: {scenarios}")
            else:
                print(f"Scenarios: {list(FAILOVER_SCENARIOS.keys())}")
        else:
            print(f"Technologies: {runner.config.technologies}")
            print(f"Distance scenarios: {runner.config.distance_scenarios}")
            print(f"Congestion scenarios: {runner.config.congestion_scenarios}")

            matrix = runner._get_test_matrix()
            print(f"\nTotal tests: {len(matrix)}")
            print("\nTest matrix:")
            for tech, dist, cong in matrix[:10]:
                print(f"  - {tech} / {dist} / {cong}")
            if len(matrix) > 10:
                print(f"  ... and {len(matrix) - 10} more")
        return 0

    # Connect to CMW500
    if not runner.connect():
        logger.error("Failed to connect to CMW500. Exiting.")
        return 1

    try:
        # Run tests based on mode
        if args.mode == "full":
            runner.run_all_tests()

        elif args.mode == "distance_sweep":
            for tech in runner.config.technologies:
                runner.run_distance_sweep(tech)
            if runner.config.generate_report:
                runner.suite_result = TestSuiteResult(
                    config=runner.config,
                    start_time=datetime.now().isoformat(),
                    end_time=datetime.now().isoformat(),
                    results=runner.results,
                    total_tests=len(runner.results),
                    passed_tests=sum(1 for r in runner.results if r.passed),
                    failed_tests=sum(1 for r in runner.results if not r.passed),
                )
                runner.generate_report()

        elif args.mode == "congestion_sweep":
            for tech in runner.config.technologies:
                runner.run_congestion_sweep(tech)
            if runner.config.generate_report:
                runner.suite_result = TestSuiteResult(
                    config=runner.config,
                    start_time=datetime.now().isoformat(),
                    end_time=datetime.now().isoformat(),
                    results=runner.results,
                    total_tests=len(runner.results),
                    passed_tests=sum(1 for r in runner.results if r.passed),
                    failed_tests=sum(1 for r in runner.results if not r.passed),
                )
                runner.generate_report()

        elif args.mode == "single":
            # Run single test for first combination
            if runner.config.technologies and runner.config.distance_scenarios and runner.config.congestion_scenarios:
                result = runner.run_single_test(
                    runner.config.technologies[0],
                    runner.config.distance_scenarios[0],
                    runner.config.congestion_scenarios[0],
                )
                if result:
                    status = "PASS" if result.passed else "FAIL"
                    print(f"\nResult: {status}")
                    print(f"  DL Throughput: {result.dl_throughput_kbps:.1f} kbps")
                    print(f"  UL Throughput: {result.ul_throughput_kbps:.1f} kbps")
                    print(f"  Signal: {result.signal_strength_dbm:.1f} dBm")

        elif args.mode == "failover":
            # Parse carriers and scenarios
            carriers = None
            if args.carriers:
                carriers = [c.strip() for c in args.carriers.split(",")]

            scenarios = None
            if args.failover_scenarios:
                scenarios = [s.strip() for s in args.failover_scenarios.split(",")]

            # Run failover tests
            runner.run_failover_tests(carriers=carriers, scenarios=scenarios)

            # Generate report
            if runner.config.generate_report:
                runner.generate_failover_report()

        elif args.mode == "triple_failover":
            # Run triple failover test (AT&T -> T-Mobile -> Verizon)
            result = runner.run_triple_failover()
            if result:
                status = "PASS" if result.passed else "FAIL"
                print(f"\nTriple Failover Result: {status}")
                print(f"  Primary: {result.primary_carrier}")
                print(f"  Final: {result.final_carrier}")
                print(f"  Total Failover Time: {result.failover_time_s:.2f}s")
                if result.failure_reason:
                    print(f"  Failure Reason: {result.failure_reason}")

            if runner.config.generate_report:
                runner.generate_failover_report()

        return 0

    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        return 1

    finally:
        runner.disconnect()


if __name__ == "__main__":
    sys.exit(main())
