"""
EC21 Carrier Failover Test Suite

Tests carrier failover behavior between AT&T, T-Mobile, and Verizon
under various trigger conditions (signal loss, degradation, network reject).

This test suite requires CMW500 with multiple signaling units or
the ability to rapidly reconfigure network parameters.
"""

import logging
import time
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .carrier_config import (
    CarrierConfig,
    FailoverScenario,
    FailoverTestResult,
    FailoverTrigger,
    CARRIER_CONFIGS,
    FAILOVER_SCENARIOS,
    get_carrier_config,
    get_all_carriers,
    get_ec21_supported_bands,
    is_band_supported,
)
from .test_config import EC21TestConfig, Technology

from ...core.client import CMW500Client

logger = logging.getLogger(__name__)


class EC21FailoverTestSuite:
    """
    Test suite for carrier failover testing on Quectel EC21.

    Tests the modem's ability to switch between carriers when
    the primary carrier becomes unavailable or degraded.
    """

    def __init__(
        self,
        client: CMW500Client,
        config: EC21TestConfig,
        ec21_variant: str = "A",
    ):
        """
        Initialize failover test suite.

        Args:
            client: CMW500 client instance
            config: Test configuration
            ec21_variant: EC21 variant (A, V, AUT)
        """
        self.client = client
        self.config = config
        self.ec21_variant = ec21_variant
        self.results: List[FailoverTestResult] = []

        # Validate carrier support for EC21 variant
        self._validate_carrier_support()

    def _validate_carrier_support(self) -> None:
        """Check which carriers are supported by the EC21 variant."""
        supported_bands = get_ec21_supported_bands(self.ec21_variant)
        logger.info(f"EC21-{self.ec21_variant} supported bands:")
        logger.info(f"  LTE: {supported_bands['lte']}")
        logger.info(f"  WCDMA: {supported_bands['wcdma']}")

        for carrier in get_all_carriers():
            compat = is_band_supported(carrier, self.ec21_variant)
            status = "supported" if compat["any"] else "NOT SUPPORTED"
            logger.info(f"  {carrier.name}: {status} (LTE: {compat['lte']}, WCDMA: {compat['wcdma']})")

    def _configure_carrier(
        self,
        carrier_config: CarrierConfig,
        power_dbm: float = -70.0,
        technology: str = "LTE",
    ) -> bool:
        """
        Configure CMW500 for a specific carrier.

        Args:
            carrier_config: Carrier configuration
            power_dbm: Signal power level
            technology: Technology to use (LTE, WCDMA)

        Returns:
            True if configuration successful
        """
        try:
            logger.info(f"Configuring CMW500 for {carrier_config.name}...")

            if technology == "LTE":
                # Get primary LTE band configuration
                primary_band = None
                for band in carrier_config.lte_bands:
                    if band.band == carrier_config.lte_primary_band:
                        primary_band = band
                        break

                if not primary_band and carrier_config.lte_bands:
                    primary_band = carrier_config.lte_bands[0]

                if not primary_band:
                    logger.error(f"No LTE bands configured for {carrier_config.name}")
                    return False

                # Configure LTE signaling
                self.client.lte.configure_cell(
                    band=primary_band.band,
                    bandwidth_mhz=primary_band.bandwidth_mhz,
                    earfcn=primary_band.earfcn,
                    cell_id=1,
                    tac=1,
                )

                # Set PLMN
                self.client.lte.set_plmn(
                    mcc=carrier_config.mcc,
                    mnc=carrier_config.mnc,
                )

                # Set power level
                self.client.lte.set_rs_epre(power_dbm)

            elif technology == "WCDMA":
                # Get primary WCDMA band configuration
                primary_band = None
                for band in carrier_config.wcdma_bands:
                    if band.band == carrier_config.wcdma_primary_band:
                        primary_band = band
                        break

                if not primary_band and carrier_config.wcdma_bands:
                    primary_band = carrier_config.wcdma_bands[0]

                if not primary_band:
                    logger.error(f"No WCDMA bands configured for {carrier_config.name}")
                    return False

                # Configure WCDMA signaling
                self.client.wcdma.configure_cell(
                    band=primary_band.band,
                    uarfcn=primary_band.uarfcn,
                )

                # Set PLMN
                self.client.wcdma.set_plmn(
                    mcc=carrier_config.mcc,
                    mnc=carrier_config.mnc,
                )

                # Set power level
                self.client.wcdma.set_cpich_power(power_dbm)

            logger.info(f"Carrier {carrier_config.name} configured successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to configure carrier {carrier_config.name}: {e}")
            return False

    def _activate_cell(self, technology: str = "LTE") -> bool:
        """
        Activate the cell for the specified technology.

        Args:
            technology: Technology to activate

        Returns:
            True if successful
        """
        try:
            if technology == "LTE":
                self.client.lte.cell_on()
            elif technology == "WCDMA":
                self.client.wcdma.cell_on()
            return True
        except Exception as e:
            logger.error(f"Failed to activate {technology} cell: {e}")
            return False

    def _deactivate_cell(self, technology: str = "LTE") -> bool:
        """
        Deactivate the cell for the specified technology.

        Args:
            technology: Technology to deactivate

        Returns:
            True if successful
        """
        try:
            if technology == "LTE":
                self.client.lte.cell_off()
            elif technology == "WCDMA":
                self.client.wcdma.cell_off()
            return True
        except Exception as e:
            logger.error(f"Failed to deactivate {technology} cell: {e}")
            return False

    def _wait_for_attach(
        self,
        technology: str = "LTE",
        timeout_s: float = 60.0,
    ) -> Tuple[bool, float]:
        """
        Wait for UE to attach to network.

        Args:
            technology: Technology to monitor
            timeout_s: Timeout in seconds

        Returns:
            Tuple of (success, attach_time_seconds)
        """
        logger.info(f"Waiting for {technology} attach (timeout: {timeout_s}s)...")
        start_time = time.time()

        while (time.time() - start_time) < timeout_s:
            try:
                if technology == "LTE":
                    state = self.client.lte.get_connection_state()
                    if state in ("ATT", "CONN", "CEST"):
                        attach_time = time.time() - start_time
                        logger.info(f"UE attached in {attach_time:.2f}s")
                        return True, attach_time
                elif technology == "WCDMA":
                    state = self.client.wcdma.get_connection_state()
                    if state in ("ATT", "CONN", "DCH"):
                        attach_time = time.time() - start_time
                        logger.info(f"UE attached in {attach_time:.2f}s")
                        return True, attach_time
            except Exception as e:
                logger.debug(f"Attach check error: {e}")

            time.sleep(0.5)

        logger.warning(f"Attach timeout after {timeout_s}s")
        return False, timeout_s

    def _get_signal_measurement(
        self,
        technology: str = "LTE",
    ) -> Tuple[float, float]:
        """
        Get current signal measurements.

        Args:
            technology: Technology to measure

        Returns:
            Tuple of (signal_strength_dbm, signal_quality)
        """
        try:
            if technology == "LTE":
                rsrp = self.client.lte.measure_rsrp()
                rsrq = self.client.lte.measure_rsrq()
                return rsrp, rsrq
            elif technology == "WCDMA":
                rscp = self.client.wcdma.measure_rscp()
                ecno = self.client.wcdma.measure_ecno()
                return rscp, ecno
        except Exception as e:
            logger.error(f"Signal measurement failed: {e}")
            return -140.0, -20.0

    def _ramp_signal(
        self,
        technology: str,
        start_dbm: float,
        end_dbm: float,
        duration_s: float,
        steps: int = 10,
    ) -> None:
        """
        Gradually ramp signal level from start to end.

        Args:
            technology: Technology to adjust
            start_dbm: Starting power level
            end_dbm: Ending power level
            duration_s: Duration of ramp
            steps: Number of steps
        """
        step_duration = duration_s / steps
        step_dbm = (end_dbm - start_dbm) / steps

        current_dbm = start_dbm
        for i in range(steps + 1):
            try:
                if technology == "LTE":
                    self.client.lte.set_rs_epre(current_dbm)
                elif technology == "WCDMA":
                    self.client.wcdma.set_cpich_power(current_dbm)

                logger.debug(f"Signal ramp step {i}/{steps}: {current_dbm:.1f} dBm")
            except Exception as e:
                logger.error(f"Signal ramp error: {e}")

            time.sleep(step_duration)
            current_dbm += step_dbm

    def _trigger_signal_loss(
        self,
        technology: str,
        loss_level_dbm: float = -140.0,
    ) -> None:
        """
        Trigger signal loss by setting very low power.

        Args:
            technology: Technology to affect
            loss_level_dbm: Power level for "loss"
        """
        logger.info(f"Triggering {technology} signal loss ({loss_level_dbm} dBm)...")
        try:
            if technology == "LTE":
                self.client.lte.set_rs_epre(loss_level_dbm)
            elif technology == "WCDMA":
                self.client.wcdma.set_cpich_power(loss_level_dbm)
        except Exception as e:
            logger.error(f"Signal loss trigger failed: {e}")

    def _trigger_network_reject(self, technology: str) -> None:
        """
        Trigger network rejection.

        Args:
            technology: Technology to reject
        """
        logger.info(f"Triggering {technology} network rejection...")
        try:
            # Send reject cause via signaling
            if technology == "LTE":
                # Reject with cause #15 (No suitable cells in tracking area)
                self.client.scpi.command("CALL:LTE:SIGN:PSWitched:ACTion REJect")
            elif technology == "WCDMA":
                # Reject registration
                self.client.scpi.command("CALL:WCDMa:SIGN:PSWitched:ACTion REJect")
        except Exception as e:
            logger.error(f"Network reject trigger failed: {e}")

    def _monitor_failover(
        self,
        scenario: FailoverScenario,
        secondary_config: CarrierConfig,
        timeout_s: float = 30.0,
    ) -> Tuple[bool, float, str, int]:
        """
        Monitor for failover to secondary carrier.

        Args:
            scenario: Failover scenario
            secondary_config: Secondary carrier config
            timeout_s: Timeout in seconds

        Returns:
            Tuple of (success, failover_time, technology, band)
        """
        logger.info(f"Monitoring for failover to {secondary_config.name}...")
        start_time = time.time()

        # Expected PLMN for secondary
        expected_plmn = secondary_config.plmn

        while (time.time() - start_time) < timeout_s:
            try:
                # Check LTE registration
                try:
                    lte_plmn = self.client.lte.get_registered_plmn()
                    if lte_plmn == expected_plmn:
                        failover_time = time.time() - start_time
                        # Get band info
                        band = self.client.lte.get_serving_band()
                        logger.info(f"Failover to {secondary_config.name} LTE Band {band} in {failover_time:.2f}s")
                        return True, failover_time, "LTE", band
                except Exception:
                    pass

                # Check WCDMA registration
                try:
                    wcdma_plmn = self.client.wcdma.get_registered_plmn()
                    if wcdma_plmn == expected_plmn:
                        failover_time = time.time() - start_time
                        band = self.client.wcdma.get_serving_band()
                        logger.info(f"Failover to {secondary_config.name} WCDMA Band {band} in {failover_time:.2f}s")
                        return True, failover_time, "WCDMA", band
                except Exception:
                    pass

            except Exception as e:
                logger.debug(f"Failover monitoring error: {e}")

            time.sleep(0.5)

        logger.warning(f"Failover timeout after {timeout_s}s")
        return False, timeout_s, "", 0

    def run_failover_test(
        self,
        scenario: FailoverScenario,
        technology: str = "LTE",
    ) -> Optional[FailoverTestResult]:
        """
        Run a single failover test scenario.

        Args:
            scenario: Failover scenario to test
            technology: Initial technology (LTE or WCDMA)

        Returns:
            FailoverTestResult or None if test failed to execute
        """
        logger.info("=" * 60)
        logger.info(f"FAILOVER TEST: {scenario.name}")
        logger.info(f"  {scenario.description}")
        logger.info("=" * 60)

        timestamp = datetime.now().isoformat()

        # Get carrier configurations
        primary_config = get_carrier_config(scenario.primary_carrier)
        secondary_config = get_carrier_config(scenario.secondary_carrier)

        if not primary_config or not secondary_config:
            logger.error("Invalid carrier configuration")
            return None

        # Initialize result
        result = FailoverTestResult(
            scenario_name=scenario.name,
            timestamp=timestamp,
            primary_carrier=primary_config.name,
            primary_technology=technology,
            primary_band=primary_config.lte_primary_band if technology == "LTE" else primary_config.wcdma_primary_band,
            primary_rsrp_dbm=0.0,
            failover_triggered=False,
            failover_successful=False,
            failover_time_s=0.0,
            final_carrier="",
            final_technology="",
            final_band=0,
            final_rsrp_dbm=0.0,
            data_session_maintained=False,
            data_interruption_time_s=0.0,
            passed=False,
        )

        try:
            # Step 1: Configure primary carrier
            logger.info(f"Step 1: Configuring primary carrier ({primary_config.name})...")
            if not self._configure_carrier(primary_config, primary_config.typical_rsrp_dbm, technology):
                result.failure_reason = "Failed to configure primary carrier"
                return result

            # Step 2: Activate cell and wait for attach
            logger.info("Step 2: Activating cell and waiting for UE attach...")
            if not self._activate_cell(technology):
                result.failure_reason = "Failed to activate primary cell"
                return result

            attach_success, attach_time = self._wait_for_attach(technology, self.config.attach_timeout_s)
            if not attach_success:
                result.failure_reason = "UE failed to attach to primary carrier"
                return result

            # Step 3: Measure initial signal
            logger.info("Step 3: Measuring initial signal quality...")
            rsrp, rsrq = self._get_signal_measurement(technology)
            result.primary_rsrp_dbm = rsrp
            logger.info(f"  Primary signal: {rsrp:.1f} dBm")

            # Step 4: Pre-configure secondary carrier (for faster failover)
            logger.info(f"Step 4: Pre-configuring secondary carrier ({secondary_config.name})...")
            # In a real multi-cell setup, we'd configure a second signaling unit
            # For single-unit testing, we prepare the configuration

            # Step 5: Trigger failover condition
            logger.info(f"Step 5: Triggering failover ({scenario.trigger.value})...")
            result.failover_triggered = True
            failover_start = time.time()

            if scenario.trigger == FailoverTrigger.SIGNAL_LOSS:
                self._trigger_signal_loss(technology, scenario.signal_loss_rsrp_dbm)

            elif scenario.trigger == FailoverTrigger.SIGNAL_DEGRADATION:
                self._ramp_signal(
                    technology,
                    primary_config.typical_rsrp_dbm,
                    scenario.degradation_rsrp_dbm,
                    scenario.signal_ramp_time_s,
                )

            elif scenario.trigger == FailoverTrigger.NETWORK_REJECT:
                self._trigger_network_reject(technology)

            elif scenario.trigger == FailoverTrigger.DATA_STALL:
                # Simulate data stall by blocking data plane
                logger.info("Simulating data stall...")
                # Implementation depends on CMW500 capabilities

            # Step 6: Deactivate primary and activate secondary
            logger.info("Step 6: Switching to secondary carrier...")
            self._deactivate_cell(technology)

            # Small delay for UE to detect loss
            time.sleep(1.0)

            # Configure and activate secondary
            if not self._configure_carrier(secondary_config, secondary_config.typical_rsrp_dbm, technology):
                result.failure_reason = "Failed to configure secondary carrier"
                return result

            if not self._activate_cell(technology):
                result.failure_reason = "Failed to activate secondary cell"
                return result

            # Step 7: Monitor for failover completion
            logger.info("Step 7: Monitoring failover completion...")
            failover_success, failover_time, final_tech, final_band = self._monitor_failover(
                scenario,
                secondary_config,
                scenario.failover_timeout_s,
            )

            result.failover_successful = failover_success
            result.failover_time_s = failover_time
            result.final_carrier = secondary_config.name if failover_success else ""
            result.final_technology = final_tech
            result.final_band = final_band

            # Step 8: Measure final signal
            if failover_success:
                logger.info("Step 8: Measuring final signal quality...")
                final_rsrp, final_rsrq = self._get_signal_measurement(final_tech)
                result.final_rsrp_dbm = final_rsrp
                logger.info(f"  Final signal: {final_rsrp:.1f} dBm")

            # Step 9: Evaluate pass/fail
            min_time, max_time = scenario.expected_failover_time_s
            if failover_success and min_time <= failover_time <= max_time:
                result.passed = True
                logger.info(f"TEST PASSED: Failover completed in {failover_time:.2f}s")
            elif failover_success:
                result.passed = False
                result.failure_reason = f"Failover time {failover_time:.2f}s outside expected range ({min_time}-{max_time}s)"
                logger.warning(f"TEST FAILED: {result.failure_reason}")
            else:
                result.passed = False
                result.failure_reason = "Failover did not complete"
                logger.warning("TEST FAILED: Failover did not complete")

            return result

        except Exception as e:
            logger.error(f"Test execution error: {e}")
            result.failure_reason = str(e)
            return result

        finally:
            # Cleanup - deactivate cells
            try:
                self._deactivate_cell("LTE")
                self._deactivate_cell("WCDMA")
            except Exception:
                pass

    def run_signal_loss_tests(self) -> List[FailoverTestResult]:
        """
        Run all signal loss failover tests.

        Returns:
            List of test results
        """
        logger.info("Running signal loss failover tests...")
        results = []

        signal_loss_scenarios = [
            name for name, scenario in FAILOVER_SCENARIOS.items()
            if scenario.trigger == FailoverTrigger.SIGNAL_LOSS
            and scenario.tertiary_carrier is None  # Skip triple failover for this
        ]

        for scenario_name in signal_loss_scenarios:
            scenario = FAILOVER_SCENARIOS[scenario_name]
            result = self.run_failover_test(scenario)
            if result:
                results.append(result)
                self.results.append(result)
            time.sleep(2)

        return results

    def run_degradation_tests(self) -> List[FailoverTestResult]:
        """
        Run all signal degradation failover tests.

        Returns:
            List of test results
        """
        logger.info("Running signal degradation failover tests...")
        results = []

        degradation_scenarios = [
            name for name, scenario in FAILOVER_SCENARIOS.items()
            if scenario.trigger == FailoverTrigger.SIGNAL_DEGRADATION
        ]

        for scenario_name in degradation_scenarios:
            scenario = FAILOVER_SCENARIOS[scenario_name]
            result = self.run_failover_test(scenario)
            if result:
                results.append(result)
                self.results.append(result)
            time.sleep(2)

        return results

    def run_triple_failover_test(self) -> Optional[FailoverTestResult]:
        """
        Run triple failover test (primary -> secondary -> tertiary).

        Returns:
            Test result or None
        """
        scenario = FAILOVER_SCENARIOS.get("triple_failover_att_first")
        if not scenario:
            logger.error("Triple failover scenario not found")
            return None

        logger.info("=" * 60)
        logger.info("TRIPLE FAILOVER TEST")
        logger.info(f"  {scenario.primary_carrier} -> {scenario.secondary_carrier} -> {scenario.tertiary_carrier}")
        logger.info("=" * 60)

        timestamp = datetime.now().isoformat()

        # Get all carrier configurations
        primary_config = get_carrier_config(scenario.primary_carrier)
        secondary_config = get_carrier_config(scenario.secondary_carrier)
        tertiary_config = get_carrier_config(scenario.tertiary_carrier)

        if not all([primary_config, secondary_config, tertiary_config]):
            logger.error("Invalid carrier configuration for triple failover")
            return None

        result = FailoverTestResult(
            scenario_name=scenario.name,
            timestamp=timestamp,
            primary_carrier=primary_config.name,
            primary_technology="LTE",
            primary_band=primary_config.lte_primary_band,
            primary_rsrp_dbm=0.0,
            failover_triggered=False,
            failover_successful=False,
            failover_time_s=0.0,
            final_carrier="",
            final_technology="",
            final_band=0,
            final_rsrp_dbm=0.0,
            data_session_maintained=False,
            data_interruption_time_s=0.0,
            passed=False,
        )

        try:
            total_failover_time = 0.0

            # Phase 1: Attach to primary
            logger.info(f"Phase 1: Attaching to {primary_config.name}...")
            self._configure_carrier(primary_config, primary_config.typical_rsrp_dbm, "LTE")
            self._activate_cell("LTE")
            attach_success, _ = self._wait_for_attach("LTE", self.config.attach_timeout_s)

            if not attach_success:
                result.failure_reason = "Failed to attach to primary carrier"
                return result

            result.primary_rsrp_dbm = self._get_signal_measurement("LTE")[0]
            result.failover_triggered = True

            # Phase 2: Failover to secondary
            logger.info(f"Phase 2: Failover to {secondary_config.name}...")
            self._trigger_signal_loss("LTE", scenario.signal_loss_rsrp_dbm)
            self._deactivate_cell("LTE")
            time.sleep(1)

            self._configure_carrier(secondary_config, secondary_config.typical_rsrp_dbm, "LTE")
            self._activate_cell("LTE")

            success, failover_time, _, _ = self._monitor_failover(
                scenario, secondary_config, scenario.failover_timeout_s / 2
            )

            if not success:
                result.failure_reason = "First failover (to secondary) failed"
                return result

            total_failover_time += failover_time
            logger.info(f"First failover completed in {failover_time:.2f}s")

            # Phase 3: Failover to tertiary
            logger.info(f"Phase 3: Failover to {tertiary_config.name}...")
            self._trigger_signal_loss("LTE", scenario.signal_loss_rsrp_dbm)
            self._deactivate_cell("LTE")
            time.sleep(1)

            self._configure_carrier(tertiary_config, tertiary_config.typical_rsrp_dbm, "LTE")
            self._activate_cell("LTE")

            success, failover_time, final_tech, final_band = self._monitor_failover(
                scenario, tertiary_config, scenario.failover_timeout_s / 2
            )

            if not success:
                result.failure_reason = "Second failover (to tertiary) failed"
                return result

            total_failover_time += failover_time
            logger.info(f"Second failover completed in {failover_time:.2f}s")

            # Record results
            result.failover_successful = True
            result.failover_time_s = total_failover_time
            result.final_carrier = tertiary_config.name
            result.final_technology = final_tech
            result.final_band = final_band
            result.final_rsrp_dbm = self._get_signal_measurement(final_tech)[0]

            # Evaluate
            min_time, max_time = scenario.expected_failover_time_s
            if min_time <= total_failover_time <= max_time:
                result.passed = True
                logger.info(f"TRIPLE FAILOVER PASSED: Total time {total_failover_time:.2f}s")
            else:
                result.failure_reason = f"Total failover time {total_failover_time:.2f}s outside expected range"
                logger.warning(f"TRIPLE FAILOVER FAILED: {result.failure_reason}")

            self.results.append(result)
            return result

        except Exception as e:
            logger.error(f"Triple failover test error: {e}")
            result.failure_reason = str(e)
            return result

        finally:
            try:
                self._deactivate_cell("LTE")
            except Exception:
                pass

    def run_all_failover_tests(self) -> List[FailoverTestResult]:
        """
        Run complete failover test suite.

        Returns:
            List of all test results
        """
        logger.info("=" * 70)
        logger.info("EC21 CARRIER FAILOVER TEST SUITE")
        logger.info("=" * 70)

        self.results = []

        # Run signal loss tests
        self.run_signal_loss_tests()

        # Run degradation tests
        self.run_degradation_tests()

        # Run triple failover test
        self.run_triple_failover_test()

        # Summary
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        logger.info("\n" + "=" * 70)
        logger.info("FAILOVER TEST SUITE COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total tests: {len(self.results)}")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Pass rate: {(passed/len(self.results)*100) if self.results else 0:.1f}%")

        return self.results

    def run_carrier_pair_test(
        self,
        primary: str,
        secondary: str,
        trigger: FailoverTrigger = FailoverTrigger.SIGNAL_LOSS,
    ) -> Optional[FailoverTestResult]:
        """
        Run failover test for a specific carrier pair.

        Args:
            primary: Primary carrier name
            secondary: Secondary carrier name
            trigger: Failover trigger type

        Returns:
            Test result or None
        """
        # Find matching scenario or create ad-hoc
        for name, scenario in FAILOVER_SCENARIOS.items():
            if (scenario.primary_carrier.lower() == primary.lower() and
                scenario.secondary_carrier.lower() == secondary.lower() and
                scenario.trigger == trigger):
                return self.run_failover_test(scenario)

        # Create ad-hoc scenario
        scenario = FailoverScenario(
            name=f"{primary}_to_{secondary}_{trigger.value}",
            description=f"Ad-hoc failover from {primary} to {secondary}",
            primary_carrier=primary,
            secondary_carrier=secondary,
            trigger=trigger,
        )

        return self.run_failover_test(scenario)

    def get_results_summary(self) -> Dict:
        """
        Get summary of all test results.

        Returns:
            Summary dictionary
        """
        if not self.results:
            return {"total": 0, "passed": 0, "failed": 0}

        passed = sum(1 for r in self.results if r.passed)

        # Group by carrier pair
        carrier_pairs = {}
        for r in self.results:
            pair = f"{r.primary_carrier} -> {r.final_carrier or 'N/A'}"
            if pair not in carrier_pairs:
                carrier_pairs[pair] = {"total": 0, "passed": 0, "avg_failover_time": 0.0}
            carrier_pairs[pair]["total"] += 1
            if r.passed:
                carrier_pairs[pair]["passed"] += 1
            carrier_pairs[pair]["avg_failover_time"] += r.failover_time_s

        # Calculate averages
        for pair in carrier_pairs:
            if carrier_pairs[pair]["total"] > 0:
                carrier_pairs[pair]["avg_failover_time"] /= carrier_pairs[pair]["total"]

        return {
            "total": len(self.results),
            "passed": passed,
            "failed": len(self.results) - passed,
            "pass_rate_percent": (passed / len(self.results)) * 100,
            "by_carrier_pair": carrier_pairs,
            "results": [asdict(r) for r in self.results],
        }
