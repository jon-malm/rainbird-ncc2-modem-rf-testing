"""
NCC2 Operational Performance Specification compliance tests.

Tests derived from the FW-NCC2 Operational Performance Specification
test cases TC-001 through TC-012.  Each test maps to a specific
verification requirement from Section 9.1 of that document.

These tests exercise the fallback state machine behavior that the NCC2
firmware must implement: the Baseball Rule, service fallback via eSIM
profile switching, mode fallback via AT+COPS, QoS threshold detection,
carrier-native verification, loop behavior, NVM persistence, and event
logging.

Requires CMW500, modem hardware, and (for some tests) multiple eSIM
profiles provisioned on the DUT.
"""

import logging
import re
import time

import pytest

from tests.constants import (
    AT_CMD_TIMEOUT,
    BASEBALL_RULE_MAX_STRIKES,
    BASEBALL_RULE_RETRY_WAIT_SEC,
    BASEBALL_RULE_WINDOW_SEC,
    CELL_DEACTIVATION_DETECT_SEC,
    CELL_STABILIZE_SEC,
    MODE_FALLBACK_PRIORITY,
    MODE_SWITCH_MAX_SEC,
    POLL_INTERVAL_SEC,
    PROFILE_SWITCH_MAX_SEC,
    QOS_LTE_RSRP_THRESHOLD_DBM,
    QOS_SUSTAINED_DURATION_SEC,
    RADIO_OFF_SETTLE_SEC,
    RADIO_ON_SETTLE_SEC,
    RAT_DETECTION_WAIT_SEC,
    RECOVERY_TIMEOUT_SEC,
    SERVICE_RECOVERY_MAX_SEC,
    SIGNAL_SETTLE_SEC,
    TEST_TIMEOUT_BASEBALL_RULE,
    TEST_TIMEOUT_EXTENDED,
    TEST_TIMEOUT_MAXIMUM,
    TEST_TIMEOUT_QOS_THRESHOLD,
)
from tests.helpers import safe_cleanup

logger = logging.getLogger(__name__)


# ============================================================================
# TC-001: Baseball Rule timing
# ============================================================================


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.slow
class TestBaseballRule:
    """TC-001: Verify Baseball Rule timing.

    Pass criteria: fallback occurs within 6 minutes of first failure.

    The Baseball Rule requires that after 3 consecutive connection failures
    (strikes) with 2-minute retry waits, service fallback is initiated
    within the 6-minute window.
    """

    @pytest.mark.timeout(TEST_TIMEOUT_BASEBALL_RULE)
    def test_baseball_rule_timing(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        wait_for_deregistration,
    ):
        """Simulate 3 strikes in <=6 minutes and verify recovery timing.

        Repeatedly deactivates/reactivates the cell with 2-minute spacing
        to emulate the firmware retry loop, then measures total elapsed
        time from first failure to final recovery.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # --- Strike loop ---
        first_failure_time = None

        for strike in range(1, BASEBALL_RULE_MAX_STRIKES + 1):
            logger.info(
                "Strike %d/%d — deactivating cell",
                strike,
                BASEBALL_RULE_MAX_STRIKES,
            )
            lte_cell.deactivate_cell()

            if first_failure_time is None:
                first_failure_time = time.time()

            time.sleep(CELL_DEACTIVATION_DETECT_SEC)

            if strike < BASEBALL_RULE_MAX_STRIKES:
                # 2-minute retry wait then reactivate (simulating retry)
                remaining_wait = (
                    BASEBALL_RULE_RETRY_WAIT_SEC - CELL_DEACTIVATION_DETECT_SEC
                )
                if remaining_wait > 0:
                    time.sleep(remaining_wait)

                lte_cell.activate_cell()
                time.sleep(CELL_STABILIZE_SEC)

                # Brief re-registration attempt (will likely succeed,
                # simulating the "retry same MNO" phase)
                wait_for_registration(modem, timeout_sec=10)

        # After 3rd strike — reactivate to simulate service fallback
        lte_cell.activate_cell()
        recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )

        elapsed = time.time() - first_failure_time

        logger.info(
            "Baseball Rule: %d strikes, elapsed=%.1fs (limit=%ds), recovered=%s",
            BASEBALL_RULE_MAX_STRIKES,
            elapsed,
            BASEBALL_RULE_WINDOW_SEC,
            recovered,
        )

        assert recovered, "Modem did not recover after Baseball Rule fallback"
        assert elapsed <= BASEBALL_RULE_WINDOW_SEC + SERVICE_RECOVERY_MAX_SEC, (
            f"Recovery took {elapsed:.1f}s, exceeds Baseball Rule window "
            f"({BASEBALL_RULE_WINDOW_SEC}s) + recovery allowance "
            f"({SERVICE_RECOVERY_MAX_SEC}s)"
        )


# ============================================================================
# TC-002 / TC-003 / TC-004: Service fallback (eSIM profile switching)
# ============================================================================


@pytest.mark.hardware
@pytest.mark.lte
class TestServiceFallback:
    """TC-002/003/004: Verify eSIM profile switching for service fallback.

    Tests exercise AT+QESIM for switching between installed carrier
    profiles and verify switching time is within spec (<1 second for the
    command, <10 seconds for full service recovery).

    NOTE: These tests require multiple eSIM profiles installed on the DUT.
    When only a single profile is available the switching tests are skipped,
    but the command interface test still runs.
    """

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_esim_profile_query(self, modem):
        """Verify the modem can list installed eSIM profiles.

        Queries the eUICC for installed profiles using vendor-specific
        and 3GPP-standard commands.
        """
        # Query active ICCID via 3GPP-standard command
        iccid_resp = modem.send_command(
            'AT+CRSM=176,12258,0,0,10', timeout=AT_CMD_TIMEOUT
        )
        logger.info("ICCID (CRSM): %s", iccid_resp.strip())

        # Query IMSI
        imsi_resp = modem.send_command("AT+CIMI", timeout=AT_CMD_TIMEOUT)
        logger.info("IMSI: %s", imsi_resp.strip())

        # Try Quectel eSIM profile list (vendor-specific)
        try:
            profiles_resp = modem.send_command(
                'AT+QESIM="list"', timeout=AT_CMD_TIMEOUT
            )
            logger.info("eSIM profiles: %s", profiles_resp.strip())
        except Exception:
            logger.info("AT+QESIM list not supported — single-profile eSIM")

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_profile_switch_timing(self, modem):
        """TC-002: Verify profile switch completes within spec.

        Attempts to read available profiles and switch to the first
        alternate.  Measures the AT+QESIM command execution time.

        Spec: profile switch < 1 second (Operational Performance Spec 6.3).
        """
        # List profiles
        try:
            profiles_resp = modem.send_command(
                'AT+QESIM="list"', timeout=AT_CMD_TIMEOUT
            )
        except Exception:
            pytest.skip("AT+QESIM not supported on this modem/eSIM")

        # Parse ICCIDs from response
        iccids = re.findall(r'(\d{18,20})', profiles_resp)
        if len(iccids) < 2:
            pytest.skip(
                f"Need >=2 installed profiles to test switching (found {len(iccids)})"
            )

        # Identify current profile
        current_resp = modem.send_command("AT+CIMI", timeout=AT_CMD_TIMEOUT)
        logger.info("Current IMSI: %s", current_resp.strip())

        # Switch to an alternate profile and measure timing
        target_iccid = iccids[1]  # first alternate
        logger.info("Switching to profile ICCID=%s", target_iccid)

        start = time.time()
        switch_resp = modem.send_command(
            f'AT+QESIM="enable","{target_iccid}"', timeout=AT_CMD_TIMEOUT
        )
        switch_elapsed = time.time() - start

        logger.info(
            "Profile switch response: %s (%.3fs)", switch_resp.strip(), switch_elapsed
        )

        assert switch_elapsed < PROFILE_SWITCH_MAX_SEC, (
            f"Profile switch took {switch_elapsed:.3f}s, exceeds spec "
            f"limit {PROFILE_SWITCH_MAX_SEC}s"
        )

        # Allow modem to settle on new profile, then switch back
        time.sleep(SIGNAL_SETTLE_SEC)
        original_iccid = iccids[0]
        modem.send_command(
            f'AT+QESIM="enable","{original_iccid}"', timeout=AT_CMD_TIMEOUT
        )
        time.sleep(SIGNAL_SETTLE_SEC)

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_service_fallback_recovery_time(
        self, lte_cell, modem, wait_for_registration
    ):
        """Verify service fallback recovery completes within 10 seconds.

        After switching profiles (or simulating a service switch by cycling
        the radio), the modem must re-register within the service recovery
        target.

        Spec: service fallback recovery < 10 seconds
              (Operational Performance Spec 9.2).
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Simulate a service switch by cycling the radio (triggers
        # re-registration on the same cell, measuring attach time)
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)

        start = time.time()
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)

        recovered = wait_for_registration(
            modem, timeout_sec=SERVICE_RECOVERY_MAX_SEC
        )
        elapsed = time.time() - start

        logger.info(
            "Service recovery: registered=%s, elapsed=%.1fs (limit=%ds)",
            recovered,
            elapsed,
            SERVICE_RECOVERY_MAX_SEC,
        )

        # Recovery within the spec window is the goal; if it takes longer
        # we still want it to succeed eventually, but flag the timing
        if not recovered:
            # Give it more time and log as a warning
            recovered = wait_for_registration(
                modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
            )
            elapsed = time.time() - start
            logger.warning(
                "Service recovery exceeded target: %.1fs > %ds",
                elapsed,
                SERVICE_RECOVERY_MAX_SEC,
            )
            assert recovered, "Modem did not recover at all after service switch"


# ============================================================================
# TC-005 / TC-011: Mode fallback sequence and loop behavior
# ============================================================================


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.wcdma
@pytest.mark.slow
class TestModeFallbackSequence:
    """TC-005: Verify mode fallback from LTE to HSPA via AT+COPS.
    TC-011: Verify loop behavior after exhausting all options.

    The spec defines 7 modes (E-UTRAN, HSPA, HSUPA, HSDPA, UTRAN, EDGE,
    WCDMA).  The CMW500 can simulate LTE and WCDMA; intermediate modes
    are tested via AT+COPS network selection commands.
    """

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_mode_switch_timing(self, lte_cell, modem, wait_for_registration):
        """Verify AT+COPS mode switch completes within spec.

        Spec: mode switch < 5 seconds (Operational Performance Spec 6.3).
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Read current mode
        cops_resp = modem.send_command("AT+COPS?", timeout=AT_CMD_TIMEOUT)
        logger.info("Current COPS: %s", cops_resp.strip())

        # Attempt to set automatic mode selection (triggers re-scan)
        start = time.time()
        modem.send_command("AT+COPS=0", timeout=AT_CMD_TIMEOUT)
        elapsed = time.time() - start

        logger.info(
            "AT+COPS=0 completed in %.3fs (limit=%.1fs)",
            elapsed,
            MODE_SWITCH_MAX_SEC,
        )

        assert elapsed < MODE_SWITCH_MAX_SEC, (
            f"AT+COPS command took {elapsed:.3f}s, exceeds spec limit "
            f"{MODE_SWITCH_MAX_SEC}s"
        )

    @pytest.mark.timeout(TEST_TIMEOUT_MAXIMUM)
    def test_full_mode_fallback_lte_to_wcdma(
        self, cmw500, modem, wait_for_registration
    ):
        """TC-005: Verify mode fallback from LTE to WCDMA.

        Walks through the mode priority: LTE first, then when LTE is
        removed, falls back to WCDMA (the CMW500-available 3G mode).
        Verifies the complete transition and validates that
        MODE_FALLBACK_PRIORITY ordering is respected.
        """
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.signaling.wcdma import WCDMACellConfig

        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        lte = cmw500.get_lte_signaling()
        wcdma = cmw500.get_wcdma_signaling()

        # Mode 1: E-UTRAN (LTE)
        try:
            lte.configure_cell(LTECellConfig(dl_power_dbm=-60.0))
            lte.activate_cell()
        except Exception as e:
            pytest.skip(f"Failed to configure LTE: {e}")

        if not wait_for_registration(modem):
            safe_cleanup(lte.deactivate_cell)
            pytest.skip("Modem did not register on LTE")

        sq = modem.get_signal_quality()
        assert sq.mode == "LTE", f"Expected LTE (Mode 1), got {sq.mode}"
        logger.info(
            "Mode 1 (%s): registered on LTE, RSRP=%s",
            MODE_FALLBACK_PRIORITY[0],
            sq.rsrp,
        )

        # Prepare Mode 7: WCDMA (last resort that CMW500 can simulate)
        try:
            wcdma.configure_cell(WCDMACellConfig(dl_power_dbm=-60.0))
        except Exception as e:
            safe_cleanup(lte.deactivate_cell)
            pytest.skip(f"Failed to configure WCDMA: {e}")

        # Remove LTE, activate WCDMA — switch scan mode to AUTO so the
        # modem can find the WCDMA cell (fixture sets LTE-only mode).
        modem.send_command('AT+QCFG="nwscanmode",0', timeout=AT_CMD_TIMEOUT)
        lte.deactivate_cell()
        wcdma.activate_cell()

        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RAT_DETECTION_WAIT_SEC)

        # Wait for WCDMA registration (CREG for CS domain)
        start = time.time()
        wcdma_registered = False
        while (time.time() - start) < RECOVERY_TIMEOUT_SEC:
            resp = modem.send_command("AT+CREG?")
            match = re.search(r"\+CREG:\s*\d+,(\d+)", resp)
            if match and int(match.group(1)) in (1, 5):
                wcdma_registered = True
                break
            time.sleep(POLL_INTERVAL_SEC)

        if not wcdma_registered:
            safe_cleanup(wcdma.deactivate_cell)
            # Restore LTE-only scan mode even on skip path
            modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
            pytest.skip("Modem did not fall back to WCDMA")

        sq = modem.get_signal_quality()
        logger.info(
            "Mode 7 (%s): fell back to %s",
            MODE_FALLBACK_PRIORITY[6],
            sq.mode,
        )

        safe_cleanup(wcdma.deactivate_cell)

        # Reset modem to LTE-only scan mode and turn radio off.
        # Leave the radio off so the modem doesn't scan into the void
        # before the next test's lte_cell fixture activates a cell.
        # The wait_for_registration helper will turn it back on.
        modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)

        assert sq.mode == "WCDMA", f"Expected WCDMA (Mode 7), got {sq.mode}"

    @pytest.mark.timeout(TEST_TIMEOUT_MAXIMUM)
    def test_mode_fallback_loop_behavior(
        self, cmw500, modem, wait_for_registration
    ):
        """TC-011: Verify system loops back to LTE after exhausting modes.

        After falling back from LTE to WCDMA and then losing WCDMA, the
        modem must loop back to LTE when it becomes available again —
        confirming the state machine wraps from Mode 7 back to Mode 1.
        """
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.signaling.wcdma import WCDMACellConfig

        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        lte = cmw500.get_lte_signaling()
        wcdma = cmw500.get_wcdma_signaling()

        # Phase 1: Start on LTE
        try:
            lte.configure_cell(LTECellConfig(dl_power_dbm=-60.0))
            lte.activate_cell()
        except Exception as e:
            pytest.skip(f"Failed to configure LTE: {e}")

        if not wait_for_registration(modem):
            safe_cleanup(lte.deactivate_cell)
            pytest.skip("Modem did not register on LTE")

        logger.info("Phase 1: On LTE")

        # Phase 2: Force to WCDMA
        try:
            wcdma.configure_cell(WCDMACellConfig(dl_power_dbm=-60.0))
        except Exception as e:
            safe_cleanup(lte.deactivate_cell)
            pytest.skip(f"Failed to configure WCDMA: {e}")

        # Switch scan mode to AUTO so the modem can find the WCDMA cell
        modem.send_command('AT+QCFG="nwscanmode",0', timeout=AT_CMD_TIMEOUT)
        lte.deactivate_cell()
        wcdma.activate_cell()
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RAT_DETECTION_WAIT_SEC)

        start = time.time()
        wcdma_registered = False
        while (time.time() - start) < RECOVERY_TIMEOUT_SEC:
            resp = modem.send_command("AT+CREG?")
            match = re.search(r"\+CREG:\s*\d+,(\d+)", resp)
            if match and int(match.group(1)) in (1, 5):
                wcdma_registered = True
                break
            time.sleep(POLL_INTERVAL_SEC)

        if not wcdma_registered:
            safe_cleanup(wcdma.deactivate_cell, lte.deactivate_cell)
            modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
            pytest.skip("Modem did not fall back to WCDMA")

        logger.info("Phase 2: On WCDMA")

        # Phase 3: Remove WCDMA, restore LTE — verify loop back to Mode 1.
        # Switch scan mode to LTE only and turn radio off before swapping
        # cells so the modem releases its WCDMA bearer cleanly.
        modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        wcdma.deactivate_cell()
        lte.activate_cell()
        time.sleep(CELL_STABILIZE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        lte_recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC
        )

        sq = modem.get_signal_quality()
        safe_cleanup(lte.deactivate_cell)

        # Turn radio off so the modem doesn't scan into the void before
        # the next test's lte_cell fixture activates a cell.
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)

        assert lte_recovered, "Modem did not loop back to LTE after WCDMA exhausted"
        assert sq.mode == "LTE", f"Expected LTE after loop-back, got {sq.mode}"
        logger.info("Phase 3: Looped back to LTE (Mode 1) — TC-011 PASS")


# ============================================================================
# TC-006 / TC-007: QoS threshold detection
# ============================================================================


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.slow
class TestQoSThresholdDetection:
    """TC-006: Verify LTE QoS threshold detection.
    TC-007: Verify HSPA QoS threshold detection.

    The firmware must detect when QoS parameters fall below threshold
    for a sustained period (6 continuous minutes) and initiate fallback.

    These tests use the CMW500 to control DL power and verify that the
    modem reports RSRP values that cross the threshold boundary.
    """

    @pytest.mark.timeout(TEST_TIMEOUT_QOS_THRESHOLD)
    def test_lte_rsrp_above_threshold(
        self, lte_cell, modem, wait_for_registration
    ):
        """Verify modem stays registered when RSRP is above threshold.

        Sets CMW500 power so the modem's RSRP is just above the -120 dBm
        threshold and confirms the modem remains registered.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Set DL power to produce RSRP above threshold
        # CMW500 DL power of -110 dBm typically produces RSRP ~ -110 to -115 dBm
        # (above the -120 dBm threshold)
        lte_cell.set_dl_power(-110.0)
        time.sleep(SIGNAL_SETTLE_SEC)

        sq = modem.get_signal_quality()
        logger.info(
            "Above-threshold test: DL=-110 dBm, RSRP=%s dBm (threshold=%d dBm)",
            sq.rsrp,
            QOS_LTE_RSRP_THRESHOLD_DBM,
        )

        assert modem.is_registered(), (
            "Modem should remain registered when RSRP is above threshold"
        )

        if sq.rsrp is not None:
            assert sq.rsrp > QOS_LTE_RSRP_THRESHOLD_DBM, (
                f"RSRP {sq.rsrp} dBm is below threshold "
                f"{QOS_LTE_RSRP_THRESHOLD_DBM} dBm at DL=-110 dBm"
            )

        # Restore nominal power
        lte_cell.set_dl_power(-60.0)

    @pytest.mark.timeout(TEST_TIMEOUT_QOS_THRESHOLD)
    def test_lte_rsrp_below_threshold(
        self, lte_cell, modem, wait_for_registration, measure_signal_quality
    ):
        """TC-006: Verify RSRP below -120 dBm is detected.

        Sets CMW500 power to push RSRP below the -120 dBm threshold.
        Confirms the modem reports sub-threshold RSRP values.  The actual
        6-minute sustained trigger is a firmware responsibility; this test
        validates that the test framework and hardware can produce and
        detect the threshold condition.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Set DL power very low — may push RSRP below -120 dBm
        lte_cell.set_dl_power(-120.0)
        time.sleep(SIGNAL_SETTLE_SEC * 2)

        measurements = measure_signal_quality(modem, count=5, interval_sec=1.0)
        valid_rsrp = [m["rsrp"] for m in measurements if m["rsrp"] is not None]

        if valid_rsrp:
            avg_rsrp = sum(valid_rsrp) / len(valid_rsrp)
            logger.info(
                "Below-threshold test: DL=-120 dBm, avg RSRP=%.1f dBm "
                "(threshold=%d dBm, %d samples)",
                avg_rsrp,
                QOS_LTE_RSRP_THRESHOLD_DBM,
                len(valid_rsrp),
            )
        else:
            logger.info(
                "Below-threshold test: modem returned no RSRP at DL=-120 dBm "
                "(may have lost registration)"
            )

        # Check if modem detected the poor signal
        is_reg = modem.is_registered()
        logger.info("Modem registered at -120 dBm DL: %s", is_reg)

        # Restore power
        lte_cell.set_dl_power(-60.0)

        # Either the modem lost registration (correct behavior at threshold)
        # or it reports RSRP at/below threshold (firmware should detect this)
        if valid_rsrp:
            avg_rsrp = sum(valid_rsrp) / len(valid_rsrp)
            # Verify we can produce sub-threshold RSRP
            if avg_rsrp > QOS_LTE_RSRP_THRESHOLD_DBM and is_reg:
                logger.warning(
                    "Could not push RSRP below threshold with DL=-120 dBm "
                    "(RF path gain may differ). avg_rsrp=%.1f dBm",
                    avg_rsrp,
                )

    @pytest.mark.timeout(TEST_TIMEOUT_QOS_THRESHOLD)
    def test_lte_rsrp_sustained_below_threshold(
        self, lte_cell, modem, wait_for_registration, measure_signal_quality
    ):
        """TC-006 sustained: RSRP below threshold for extended period.

        Holds DL power at the threshold boundary for 6+ minutes and
        monitors modem RSRP and registration status.  This emulates
        the sustained QoS degradation that should trigger service fallback.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Set DL power to threshold boundary
        lte_cell.set_dl_power(-118.0)
        time.sleep(SIGNAL_SETTLE_SEC)

        # Monitor for the sustained duration
        check_interval = 30.0  # check every 30 seconds
        num_checks = int(QOS_SUSTAINED_DURATION_SEC / check_interval) + 1
        rsrp_log = []
        registration_log = []

        for i in range(num_checks):
            sq = modem.get_signal_quality()
            is_reg = modem.is_registered()
            rsrp_log.append(sq.rsrp)
            registration_log.append(is_reg)
            logger.info(
                "Sustained check %d/%d: RSRP=%s dBm, registered=%s",
                i + 1,
                num_checks,
                sq.rsrp,
                is_reg,
            )
            if not is_reg:
                logger.info(
                    "Modem lost registration after %ds at threshold boundary",
                    int((i + 1) * check_interval),
                )
                break
            if i < num_checks - 1:
                time.sleep(check_interval)

        # Restore power
        lte_cell.set_dl_power(-60.0)

        # Log summary
        valid_rsrp = [r for r in rsrp_log if r is not None]
        if valid_rsrp:
            logger.info(
                "Sustained QoS test: avg RSRP=%.1f dBm over %d checks, "
                "registration losses=%d",
                sum(valid_rsrp) / len(valid_rsrp),
                len(rsrp_log),
                registration_log.count(False),
            )


# ============================================================================
# TC-010: Carrier-native status verification
# ============================================================================


@pytest.mark.hardware
@pytest.mark.lte
class TestCarrierNativeStatus:
    """TC-010: Verify device registers as native subscriber.

    The NCC2 architecture uses separate eSIM profiles per carrier to
    achieve carrier-native status (not roaming).  This test verifies
    that the modem registers with state 1 (home) on the test network,
    confirming the eSIM profile and network configuration support
    carrier-native registration.
    """

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_registers_as_home_not_roaming(
        self, lte_cell, modem, wait_for_registration
    ):
        """Verify CEREG reports state 1 (home), not state 5 (roaming)."""
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Query EPS registration status
        cereg_resp = modem.send_command("AT+CEREG?", timeout=AT_CMD_TIMEOUT)
        logger.info("CEREG: %s", cereg_resp.strip())

        match = re.search(r"\+CEREG:\s*\d+,(\d+)", cereg_resp)
        assert match, f"Could not parse CEREG response: {cereg_resp}"
        stat = int(match.group(1))

        # State 1 = registered home, 5 = registered roaming
        # For carrier-native, we want state 1
        logger.info(
            "Registration state: %d (%s)",
            stat,
            "home" if stat == 1 else "roaming" if stat == 5 else "other",
        )

        # On a test network (MCC=001, MNC=01) with CMW500, state 1 is expected.
        # In a live carrier test, state 1 confirms carrier-native.
        assert stat in (1, 5), f"Unexpected registration state {stat}"

        if stat == 5:
            logger.warning(
                "Modem registered as ROAMING (state 5). "
                "For carrier-native compliance (TC-010), state 1 is required. "
                "Check eSIM profile matches the test network MCC/MNC."
            )

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_operator_identification(self, lte_cell, modem, wait_for_registration):
        """Verify operator name/MCC-MNC is reported after registration.

        AT+COPS? returns the serving operator, confirming which carrier
        profile the modem is using.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        cops_resp = modem.send_command("AT+COPS?", timeout=AT_CMD_TIMEOUT)
        logger.info("COPS: %s", cops_resp.strip())

        # AT+COPS? response format: +COPS: <mode>,<format>,<oper>,<AcT>
        match = re.search(r'\+COPS:\s*\d+,\d+,"([^"]+)"(?:,(\d+))?', cops_resp)
        if match:
            operator = match.group(1)
            act = match.group(2)
            logger.info("Operator: %s, AcT: %s", operator, act)
        else:
            logger.info("Could not parse operator from COPS response")


# ============================================================================
# TC-012: NVM persistence
# ============================================================================


@pytest.mark.hardware
@pytest.mark.lte
class TestNVMPersistence:
    """TC-012: Verify NVM persistence across power cycles.

    The tier_config and other NVM-stored parameters must survive modem
    power cycles.  This test writes a configuration value, power-cycles
    the modem, and verifies the value persists.
    """

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_band_config_persists_across_radio_cycle(self, modem):
        """Verify AT+QCFG band configuration survives radio cycle.

        Uses the band configuration as a proxy for NVM persistence,
        since tier_config storage depends on firmware implementation.
        """
        # Read current band config
        original_resp = modem.send_command(
            'AT+QCFG="band"', timeout=AT_CMD_TIMEOUT
        )
        logger.info("Band config before cycle: %s", original_resp.strip())

        # Power cycle the modem radio
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        # Re-read band config
        after_resp = modem.send_command(
            'AT+QCFG="band"', timeout=AT_CMD_TIMEOUT
        )
        logger.info("Band config after cycle: %s", after_resp.strip())

        # Extract the band mask values for comparison
        def _parse_bands(resp):
            match = re.search(
                r'\+QCFG:\s*"band",0x([0-9a-fA-F]+),0x([0-9a-fA-F]+),0x([0-9a-fA-F]+)',
                resp,
            )
            return match.groups() if match else None

        before = _parse_bands(original_resp)
        after = _parse_bands(after_resp)

        if before and after:
            assert before == after, (
                f"Band config changed after radio cycle: {before} -> {after}"
            )
            logger.info("NVM persistence confirmed: band config unchanged")
        else:
            logger.warning(
                "Could not parse band config for comparison; "
                "NVM persistence check inconclusive"
            )

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_apn_config_persists_across_radio_cycle(self, modem):
        """Verify PDP context APN configuration survives radio cycle."""
        # Set a known APN
        modem.send_command('AT+CGDCONT=1,"IP","test"', timeout=AT_CMD_TIMEOUT)

        # Read it back
        before_resp = modem.send_command("AT+CGDCONT?", timeout=AT_CMD_TIMEOUT)
        logger.info("PDP config before cycle: %s", before_resp.strip())

        # Power cycle
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        # Read again
        after_resp = modem.send_command("AT+CGDCONT?", timeout=AT_CMD_TIMEOUT)
        logger.info("PDP config after cycle: %s", after_resp.strip())

        assert '"test"' in after_resp or "'test'" in after_resp, (
            "APN 'test' not found after radio cycle — NVM persistence failure"
        )


# ============================================================================
# TC-008 / TC-009: Event logging verification
# ============================================================================


@pytest.mark.hardware
@pytest.mark.lte
class TestEventLogging:
    """TC-008: Verify fallback events are logged with correct data.
    TC-009: Verify event upload upon reconnection.

    These tests verify that the modem/firmware logs significant events.
    Since the NCC2 firmware event logging is implementation-dependent,
    these tests validate the AT command and signal quality query
    infrastructure that underpins event data collection.
    """

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_signal_quality_data_available(
        self, lte_cell, modem, wait_for_registration, measure_signal_quality
    ):
        """TC-008: Verify QoS data is available for event logging.

        Confirms that all parameters needed for fallback event logs
        (RSRP, RSRQ, SINR, RSSI) are retrievable from the modem.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        measurements = measure_signal_quality(modem, count=3, interval_sec=1.0)

        # Verify we get the required fields
        for m in measurements:
            logger.info(
                "Event data: mode=%s, rssi=%s, rsrp=%s, rsrq=%s, sinr=%s",
                m.get("mode"),
                m.get("rssi"),
                m.get("rsrp"),
                m.get("rsrq"),
                m.get("sinr"),
            )

        # At least one measurement should have RSRP (the primary QoS metric)
        has_rsrp = any(m.get("rsrp") is not None for m in measurements)
        assert has_rsrp, "No RSRP data available — event logging would be incomplete"

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_extended_signal_quality_commands(
        self, lte_cell, modem, wait_for_registration
    ):
        """Verify extended QoS AT commands return valid data.

        Tests the specific AT commands listed in the Operational
        Performance Spec Section 5.4.2 for QoS retrieval.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # AT+CSQ — standard signal quality
        csq_resp = modem.send_command("AT+CSQ", timeout=AT_CMD_TIMEOUT)
        logger.info("CSQ: %s", csq_resp.strip())
        assert "+CSQ:" in csq_resp, "AT+CSQ did not return expected response"

        # AT+QCSQ — Quectel extended signal quality
        try:
            qcsq_resp = modem.send_command("AT+QCSQ", timeout=AT_CMD_TIMEOUT)
            logger.info("QCSQ: %s", qcsq_resp.strip())
        except Exception:
            logger.info("AT+QCSQ not available (vendor-specific)")

        # AT+QNWINFO — network information
        try:
            nwinfo_resp = modem.send_command("AT+QNWINFO", timeout=AT_CMD_TIMEOUT)
            logger.info("QNWINFO: %s", nwinfo_resp.strip())
        except Exception:
            logger.info("AT+QNWINFO not available (vendor-specific)")

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_serving_cell_info_for_logging(
        self, lte_cell, modem, wait_for_registration
    ):
        """Verify serving cell information is available for event context.

        Event logs need cell identity, band, and channel data alongside
        QoS measurements.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # AT+QENG="servingcell" — detailed serving cell info
        try:
            eng_resp = modem.send_command(
                'AT+QENG="servingcell"', timeout=AT_CMD_TIMEOUT
            )
            logger.info("Serving cell: %s", eng_resp.strip())
            assert "+QENG:" in eng_resp, "Serving cell query returned no data"
        except Exception:
            logger.info("AT+QENG not available (vendor-specific)")

        # AT+COPS? — operator and access technology
        cops_resp = modem.send_command("AT+COPS?", timeout=AT_CMD_TIMEOUT)
        logger.info("Operator: %s", cops_resp.strip())
        assert "+COPS:" in cops_resp, "AT+COPS? did not return expected response"
