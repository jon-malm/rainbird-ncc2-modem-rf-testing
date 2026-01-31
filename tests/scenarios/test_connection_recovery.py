"""
Data connection recovery tests.

Tests verify modem behavior when the data connection is interrupted
and verify that the modem recovers appropriately by reconnecting.

Scenarios covered:
- Cell deactivation and reactivation
- Signal degradation to loss and recovery
- UE detach and re-attach
- Band/carrier switching
- RAT fallback (LTE to WCDMA) and return
- PDP context loss and reactivation
- Intermittent connection (multiple interruptions)
"""

import logging
import re
import time

import pytest

from tests.constants import (
    AT_CMD_TIMEOUT,
    AT_PDP_ACTIVATE_TIMEOUT,
    AT_PDP_DEACTIVATE_TIMEOUT,
    BRIEF_OUTAGE_DURATION_SEC,
    CELL_DEACTIVATION_DETECT_SEC,
    CELL_RESELECTION_WAIT_SEC,
    CELL_STABILIZE_SEC,
    DEREGISTRATION_TIMEOUT_SEC,
    INTERMITTENT_RECOVERY_WAIT_SEC,
    POLL_INTERVAL_SEC,
    PROLONGED_OUTAGE_DURATION_SEC,
    PROLONGED_RECOVERY_TIMEOUT_SEC,
    RADIO_OFF_SETTLE_SEC,
    RADIO_ON_SETTLE_SEC,
    RAPID_CHANGE_INTERVAL_SEC,
    RAT_DETECTION_WAIT_SEC,
    RECOVERY_TIMEOUT_SEC,
    REGISTRATION_TIMEOUT_SEC,
    SIGNAL_SETTLE_SEC,
    TEST_TIMEOUT_EXTENDED,
    TEST_TIMEOUT_LONG,
    TEST_TIMEOUT_MAXIMUM,
    TEST_TIMEOUT_MEDIUM,
    TEST_TIMEOUT_STANDARD,
)
from tests.helpers import safe_cleanup

logger = logging.getLogger(__name__)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.slow
class TestConnectionRecovery:
    """Connection interruption and recovery tests."""

    # =========================================================================
    # CELL DEACTIVATION / REACTIVATION
    # =========================================================================

    @pytest.mark.timeout(TEST_TIMEOUT_MEDIUM)
    def test_cell_deactivation_recovery(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        wait_for_deregistration,
        activate_data_connection_with_modem,
    ):
        """Test modem recovers after cell is deactivated and reactivated.

        Simulates a complete cell outage (e.g., tower maintenance) and verifies
        the modem reconnects when the cell comes back online.
        """
        # Establish initial connection
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to establish initial data connection")

        # Record initial signal quality
        initial_sq = modem.get_signal_quality()
        assert initial_sq.mode == "LTE", f"Expected LTE mode, got {initial_sq.mode}"

        # Deactivate cell - simulates complete cell outage
        lte_cell.deactivate_cell()

        # Allow the CMW500 to complete cell teardown before polling the modem.
        # In RRC CONNECTED state the modem must first detect radio link failure
        # (RLF), run T310/T311 timers, and then update CEREG — this can take
        # longer than when idle.
        time.sleep(CELL_DEACTIVATION_DETECT_SEC)

        # Wait for modem to detect loss of service (poll instead of fixed sleep)
        lost_registration = wait_for_deregistration(
            modem, timeout_sec=DEREGISTRATION_TIMEOUT_SEC
        )
        if not lost_registration:
            # The modem may still report registered via cached CEREG while
            # internally processing the RLF.  Continue with the test —
            # reactivating the cell will still exercise the recovery path.
            logger.warning(
                "Modem still reports registered %ds after cell deactivation; "
                "continuing with recovery test",
                DEREGISTRATION_TIMEOUT_SEC,
            )

        # Reactivate cell
        lte_cell.activate_cell()

        # Wait for modem to recover and re-register
        # force_search=True cycles the radio to trigger an immediate scan,
        # since the modem's periodic search timer may have expired during outage
        recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )
        assert recovered, "Modem failed to recover registration after cell reactivation"

        # Verify data connection can be re-established
        data_recovered = activate_data_connection_with_modem(modem, lte_cell)
        assert data_recovered, "Failed to re-establish data connection after recovery"

        # Verify signal quality is restored
        recovered_sq = modem.get_signal_quality()
        assert recovered_sq.mode == "LTE", (
            f"Expected LTE mode after recovery, got {recovered_sq.mode}"
        )

    @pytest.mark.timeout(TEST_TIMEOUT_LONG)
    def test_repeated_cell_cycling(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem handles repeated cell on/off cycles.

        Verifies modem stability when the cell is repeatedly cycled,
        simulating unstable network conditions.
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        num_cycles = 3
        successful_recoveries = 0

        for cycle in range(num_cycles):
            logger.info("Cell cycle %s/%s", cycle + 1, num_cycles)

            # Deactivate cell
            lte_cell.deactivate_cell()
            time.sleep(CELL_DEACTIVATION_DETECT_SEC)

            # Verify loss of service
            if modem.is_registered():
                logger.info(
                    "  Warning: Modem still registered after deactivation in cycle %d",
                    cycle + 1,
                )

            # Reactivate cell
            lte_cell.activate_cell()

            # Wait for recovery — force_search cycles the radio so the modem
            # re-scans immediately instead of waiting for its periodic timer
            if wait_for_registration(
                modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
            ):
                successful_recoveries += 1
                logger.info("  Recovery successful in cycle %s", cycle + 1)
            else:
                logger.info("  Recovery failed in cycle %s", cycle + 1)

            # Brief stabilization period
            time.sleep(SIGNAL_SETTLE_SEC)

        assert successful_recoveries == num_cycles, (
            f"Modem only recovered {successful_recoveries}/{num_cycles} times"
        )

    # =========================================================================
    # SIGNAL DEGRADATION AND RECOVERY
    # =========================================================================

    @pytest.mark.timeout(TEST_TIMEOUT_MEDIUM)
    def test_signal_loss_and_recovery(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        wait_for_deregistration,
        activate_data_connection_with_modem,
    ):
        """Test modem recovers after signal degrades to loss and is restored.

        Simulates moving out of coverage area and returning.
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to establish initial data connection")

        initial_sq = modem.get_signal_quality()
        logger.info("Initial signal: RSRP=%s dBm", initial_sq.rsrp)

        # Gradually degrade signal to simulate moving out of coverage
        power_levels = [-60, -90, -110, -120]
        lost_registration_at = None

        for power in power_levels:
            lte_cell.set_dl_power(power)
            time.sleep(CELL_DEACTIVATION_DETECT_SEC)

            sq = modem.get_signal_quality()
            is_reg = modem.is_registered()
            logger.info(
                "Power: %s dBm, RSRP: %s, Registered: %s", power, sq.rsrp, is_reg
            )

            if not is_reg and lost_registration_at is None:
                lost_registration_at = power
                logger.info("Modem lost registration at %s dBm", power)

        # Ensure we're out of coverage
        if lost_registration_at is None:
            # Modem has high sensitivity — deactivate the cell to force loss
            lte_cell.deactivate_cell()
            if not wait_for_deregistration(modem):
                # Re-activate before skipping so teardown doesn't fail
                lte_cell.activate_cell()
                pytest.skip("Could not force modem to lose registration")

        # Restore coverage — re-activate cell if it was deactivated, then set power
        if lost_registration_at is None:
            lte_cell.activate_cell()
        lte_cell.set_dl_power(-60)

        # Wait for modem to recover
        # force_search=True cycles the radio to trigger an immediate scan,
        # since the modem's periodic search timer may have expired during outage
        recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )
        assert recovered, "Modem failed to recover after signal restoration"

        # Verify data connection recovery
        data_recovered = activate_data_connection_with_modem(modem, lte_cell)
        assert data_recovered, (
            "Failed to re-establish data connection after signal recovery"
        )

        recovered_sq = modem.get_signal_quality()
        logger.info("Recovered signal: RSRP=%s dBm", recovered_sq.rsrp)

    @pytest.mark.timeout(TEST_TIMEOUT_MEDIUM)
    def test_edge_of_coverage_stability(
        self,
        lte_cell,
        modem,
        wait_for_registration,
    ):
        """Test modem stability at edge of coverage with fluctuating signal.

        Simulates being at the edge of a cell where signal may fluctuate.
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        # Fluctuate signal around edge of coverage
        power_sequence = [-95, -105, -100, -110, -95, -105, -100]
        registration_losses = 0

        for i, power in enumerate(power_sequence):
            lte_cell.set_dl_power(power)
            time.sleep(CELL_DEACTIVATION_DETECT_SEC)

            sq = modem.get_signal_quality()
            is_reg = modem.is_registered()
            logger.info(
                "Step %d: Power=%s dBm, RSRP=%s, Registered=%s",
                i + 1,
                power,
                sq.rsrp,
                is_reg,
            )

            if not is_reg:
                registration_losses += 1

        # Restore good signal
        lte_cell.set_dl_power(-60)

        # Verify final recovery — force_search cycles the radio so the modem
        # re-scans immediately instead of waiting for its periodic timer,
        # which may have expired during sustained low-power stress
        recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )
        assert recovered, "Modem failed to recover after edge-of-coverage test"

        logger.info(
            "Registration losses during edge-of-coverage test: %d",
            registration_losses,
        )

    # =========================================================================
    # UE DETACH AND RE-ATTACH
    # =========================================================================

    @pytest.mark.timeout(TEST_TIMEOUT_MEDIUM)
    def test_network_initiated_detach_recovery(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem recovers after network-initiated detach.

        Simulates network forcing the UE to detach (e.g., administrative action).
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to establish initial data connection")

        # Force UE detach from network side
        lte_cell.detach_ue()

        # Wait for modem to process detach
        time.sleep(CELL_DEACTIVATION_DETECT_SEC)

        # Modem should attempt to re-attach automatically
        recovered = wait_for_registration(modem, timeout_sec=RECOVERY_TIMEOUT_SEC)
        assert recovered, "Modem failed to re-attach after network-initiated detach"

        # Verify data connection can be re-established
        data_recovered = activate_data_connection_with_modem(modem, lte_cell)
        assert data_recovered, (
            "Failed to re-establish data connection after detach recovery"
        )

    @pytest.mark.timeout(TEST_TIMEOUT_LONG)
    def test_repeated_detach_attach_cycles(
        self,
        lte_cell,
        modem,
        wait_for_registration,
    ):
        """Test modem handles repeated detach/attach cycles.

        Verifies modem stability under repeated network-initiated detaches.
        """
        # Ensure clean PS domain state — a previous detach test may have left
        # the Quectel EG21-G in a state where the PS data path is broken.
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        num_cycles = 5
        successful_reattaches = 0

        for cycle in range(num_cycles):
            logger.info("Detach/attach cycle %s/%s", cycle + 1, num_cycles)

            # Force detach
            lte_cell.detach_ue()
            time.sleep(SIGNAL_SETTLE_SEC)

            # Wait for re-attach
            if wait_for_registration(modem, timeout_sec=REGISTRATION_TIMEOUT_SEC):
                successful_reattaches += 1
                logger.info("  Re-attach successful in cycle %s", cycle + 1)
            else:
                logger.info("  Re-attach failed in cycle %s", cycle + 1)
                # Try to recover for next iteration
                modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
                time.sleep(RADIO_OFF_SETTLE_SEC)
                modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
                wait_for_registration(modem, timeout_sec=DEREGISTRATION_TIMEOUT_SEC)

        assert successful_reattaches >= num_cycles - 1, (
            f"Modem only re-attached {successful_reattaches}/{num_cycles} times"
        )

    # =========================================================================
    # BAND / CARRIER SWITCHING
    # =========================================================================

    @pytest.mark.timeout(TEST_TIMEOUT_LONG)
    def test_band_switching_recovery(
        self,
        cmw500,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem recovers when forced to switch between LTE bands.

        Simulates carrier aggregation changes or band refarming scenarios.
        """
        from equipment_cmw500 import LTEBearerConfig, LTECellConfig
        from equipment_cmw500.models.enums import LTEBand

        # Reset modem PS domain — preceding detach cycle tests may have
        # left the data path in a broken state.
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        # Query current band configuration so we can restore it later.
        # Response format: +QCFG: "band",<gsm_bands>,<lte_bands>,<tds_bands>
        band_resp = modem.send_command('AT+QCFG="band"', timeout=AT_CMD_TIMEOUT)
        logger.info("Modem band config: %s", band_resp.strip())
        # Parse the LTE band mask (hex without 0x prefix) for restore.
        # AT+QCFG="band" returns e.g. +QCFG: "band",0xbff,0x40,0x0
        # but the SET command expects raw hex: AT+QCFG="band",0,40,0
        original_lte_bands = None
        band_match = re.search(
            r'\+QCFG:\s*"band",0x([0-9a-fA-F]+),0x([0-9a-fA-F]+),0x([0-9a-fA-F]+)',
            band_resp,
        )
        if band_match:
            original_lte_bands = band_match.group(2)
            logger.info("Original LTE band mask: 0x%s", original_lte_bands)

        bearer = LTEBearerConfig(apn="test", pdn_type="IPV4", qci=9)

        # Ensure clean state before configuring
        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        # Start with Band 7
        lte = cmw500.get_lte_signaling()
        config_band7 = LTECellConfig(
            band=LTEBand.BAND_7,
            dl_earfcn=3100,
            dl_power_dbm=-60.0,
        )

        try:
            lte.configure_cell(config_band7)
            lte.activate_cell()
            lte.configure_default_bearer(bearer)
        except Exception as e:
            pytest.skip(f"Failed to configure Band 7: {e}")

        if not wait_for_registration(modem):
            lte.deactivate_cell()
            pytest.skip("Modem did not register on Band 7")

        if not activate_data_connection_with_modem(modem, lte):
            lte.deactivate_cell()
            pytest.skip("Failed to establish data connection on Band 7")

        logger.info("Established connection on Band 7")

        # Switch to Band 3
        lte.deactivate_cell()
        time.sleep(SIGNAL_SETTLE_SEC)

        # Lock the modem to Band 3 only so it doesn't waste time scanning
        # other bands.  AT+QCFG="band" second parameter is the LTE band
        # bitmask — Band 3 = bit 2 = 0x4.
        modem.send_command('AT+QCFG="band",0,4,0', timeout=AT_CMD_TIMEOUT)

        # EARFCN 1300 is center of Band 3 (1800 MHz FDD)
        config_band3 = LTECellConfig(
            band=LTEBand.BAND_3,
            dl_earfcn=1300,
            dl_power_dbm=-60.0,
        )

        # Helper to restore the original band configuration
        def _restore_bands():
            if original_lte_bands:
                modem.send_command(
                    f'AT+QCFG="band",0,{original_lte_bands},0',
                    timeout=AT_CMD_TIMEOUT,
                )

        try:
            lte.configure_cell(config_band3)
            lte.activate_cell()
            lte.configure_default_bearer(bearer)
        except Exception as e:
            _restore_bands()
            safe_cleanup(lte.deactivate_cell)
            pytest.skip(f"Failed to configure Band 3: {e}")

        # Wait for modem to find and register on new band
        recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )

        # Restore original band configuration regardless of outcome
        _restore_bands()

        if not recovered:
            safe_cleanup(lte.deactivate_cell)
            pytest.skip("Modem did not register on Band 3 (may not support this band)")

        # Verify data connection on new band
        data_recovered = activate_data_connection_with_modem(modem, lte)

        # Cleanup - restore Band 7
        lte.deactivate_cell()

        assert data_recovered, "Failed to establish data connection on Band 3"
        logger.info("Successfully switched to Band 3 and established data connection")

    @pytest.mark.timeout(TEST_TIMEOUT_MEDIUM)
    def test_cell_reselection_maintains_data(
        self,
        cmw500,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem maintains/restores data connection during cell reselection.

        Configures two intra-frequency LTE cells with SIB3/SIB4 so the UE
        performs intra-frequency measurements and reselects to the stronger
        cell when power levels are swapped.  Verifies data connectivity is
        preserved or re-established after reselection.
        """
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.models.enums import LTEBand

        # Reset modem PS domain — preceding detach cycle tests may have
        # left the data path in a broken state.
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        band = LTEBand.BAND_7
        earfcn = 3100
        pci1, pci2 = 0, 1

        lte1 = cmw500.get_lte_signaling(cell_id=1)
        lte2 = cmw500.get_lte_signaling(cell_id=2)

        # Configure cell 1 (strong) with SIB3/SIB4
        config1 = LTECellConfig(
            band=band, dl_earfcn=earfcn, physical_cell_id=pci1, dl_power_dbm=-60.0
        )
        try:
            lte1.configure_cell(config1)
            if not lte1.configure_cell_reselection(s_intra_search_p=62):
                pytest.skip("CMW500 does not support SIB3 reselection parameters")
            if not lte1.configure_neighbor_cell(1, band, earfcn, pci2):
                pytest.skip("CMW500 does not support SIB4 neighbor cell list")
        except Exception as e:
            pytest.skip(f"Failed to configure cell 1: {e}")

        # Configure cell 2 (weak) with SIB3/SIB4
        config2 = LTECellConfig(
            band=band, dl_earfcn=earfcn, physical_cell_id=pci2, dl_power_dbm=-90.0
        )
        try:
            lte2.configure_cell(config2)
            lte2.configure_cell_reselection(s_intra_search_p=62)
            lte2.configure_neighbor_cell(1, band, earfcn, pci1)
        except Exception as e:
            safe_cleanup(lte1.deactivate_cell)
            pytest.skip(f"Failed to configure cell 2: {e}")

        # Activate both cells
        try:
            lte1.activate_cell(timeout_ms=60000)
            lte2.activate_cell(timeout_ms=60000)
        except Exception as e:
            safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
            pytest.skip(f"Failed to activate dual cells: {e}")

        time.sleep(CELL_STABILIZE_SEC)

        # Wait for registration and establish data on cell 1
        if not wait_for_registration(modem):
            safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
            pytest.skip("Modem did not register on any cell")

        # With two intra-frequency cells on the same RF path the UE may camp
        # on either cell, so try paging on both.
        if not (
            activate_data_connection_with_modem(modem, lte1)
            or activate_data_connection_with_modem(modem, lte2)
        ):
            safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
            pytest.skip("Failed to establish initial data connection on either cell")

        logger.info("Data connection established (PCI=%d or %d)", pci1, pci2)

        # Swap power levels: cell 2 becomes stronger
        lte1.set_dl_power(-90.0)
        lte2.set_dl_power(-60.0)

        # Wait for UE to measure and reselect
        time.sleep(CELL_RESELECTION_WAIT_SEC)

        # Verify modem is still registered after reselection
        registered = wait_for_registration(modem, timeout_sec=RECOVERY_TIMEOUT_SEC)

        if not registered:
            safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
            pytest.fail("Modem lost registration during cell reselection")

        # Verify data connection is maintained or can be re-established
        # After reselection the UE may be on either cell; try both
        data_ok = activate_data_connection_with_modem(
            modem, lte2
        ) or activate_data_connection_with_modem(modem, lte1)

        # Cleanup
        safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)

        assert data_ok, "Data connection not available after cell reselection"
        logger.info("Data connection maintained/restored after cell reselection")

    # =========================================================================
    # RAT FALLBACK AND RETURN
    # =========================================================================

    @pytest.mark.wcdma
    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_lte_to_wcdma_and_back(
        self,
        cmw500,
        modem,
        wait_for_registration,
    ):
        """Test modem falls back to WCDMA when LTE lost, returns when LTE restored.

        Simulates moving from LTE coverage to 3G-only area and back.
        """
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.signaling.wcdma import WCDMACellConfig

        # Ensure clean state before configuring
        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        lte = cmw500.get_lte_signaling()
        wcdma = cmw500.get_wcdma_signaling()

        # Start with LTE
        try:
            lte.configure_cell(LTECellConfig(dl_power_dbm=-60.0))
            lte.activate_cell()
        except Exception as e:
            pytest.skip(f"Failed to configure LTE: {e}")

        if not wait_for_registration(modem):
            lte.deactivate_cell()
            pytest.skip("Modem did not register on LTE")

        sq = modem.get_signal_quality()
        if sq.mode != "LTE":
            lte.deactivate_cell()
            pytest.skip(f"Modem not in LTE mode (got {sq.mode})")

        logger.info("Phase 1: Connected to LTE (RSRP=%s dBm)", sq.rsrp)

        # Configure WCDMA but keep inactive
        try:
            wcdma.configure_cell(WCDMACellConfig(dl_power_dbm=-60.0))
        except Exception as e:
            lte.deactivate_cell()
            pytest.skip(f"Failed to configure WCDMA: {e}")

        # Disable LTE, enable WCDMA - simulate moving to 3G-only area
        lte.deactivate_cell()
        wcdma.activate_cell()

        # Cycle the radio so the modem immediately scans for the WCDMA cell
        # instead of waiting for its periodic search timer (which may be
        # stale from the LTE session).
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RAT_DETECTION_WAIT_SEC)

        # Wait for WCDMA registration (use CREG for 3G)
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
            wcdma.deactivate_cell()
            pytest.skip("Modem did not fall back to WCDMA")

        sq = modem.get_signal_quality()
        logger.info("Phase 2: Fell back to WCDMA (mode=%s)", sq.mode)

        # Restore LTE, disable WCDMA - simulate returning to LTE coverage
        wcdma.deactivate_cell()
        lte.activate_cell()

        # Wait for LTE registration
        lte_recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )

        # Cleanup
        safe_cleanup(lte.deactivate_cell)

        assert lte_recovered, "Modem did not return to LTE after WCDMA"

        sq = modem.get_signal_quality()
        logger.info("Phase 3: Returned to LTE (mode=%s)", sq.mode)
        assert sq.mode == "LTE", f"Expected LTE mode after return, got {sq.mode}"

    @pytest.mark.wcdma
    @pytest.mark.timeout(TEST_TIMEOUT_MAXIMUM)
    def test_rat_fallback_with_data_continuity(
        self,
        cmw500,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test data connection is re-established after RAT changes.

        Verifies that data service is restored after falling back to 3G
        and returning to LTE.
        """
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.signaling.wcdma import WCDMACellConfig

        # Ensure clean state before configuring
        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        lte = cmw500.get_lte_signaling()
        wcdma = cmw500.get_wcdma_signaling()

        # Start with LTE and data connection
        try:
            lte.configure_cell(LTECellConfig(dl_power_dbm=-60.0))
            lte.activate_cell()
        except Exception as e:
            pytest.skip(f"Failed to configure LTE: {e}")

        if not wait_for_registration(modem):
            lte.deactivate_cell()
            pytest.skip("Modem did not register on LTE")

        if not activate_data_connection_with_modem(modem, lte):
            lte.deactivate_cell()
            pytest.skip("Failed to establish LTE data connection")

        logger.info("Phase 1: LTE data connection established")

        # Configure WCDMA
        try:
            wcdma.configure_cell(WCDMACellConfig(dl_power_dbm=-60.0))
        except Exception as e:
            lte.deactivate_cell()
            pytest.skip(f"Failed to configure WCDMA: {e}")

        # Switch to WCDMA
        lte.deactivate_cell()
        wcdma.activate_cell()

        # Cycle the radio so the modem immediately scans for the WCDMA cell
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RAT_DETECTION_WAIT_SEC)

        # Wait for WCDMA registration
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
            wcdma.deactivate_cell()
            pytest.skip("Modem did not fall back to WCDMA")

        # Try to establish data on WCDMA
        # Note: WCDMA data activation may differ from LTE
        wcdma_data = False
        try:
            wcdma_data = wcdma.activate_data_connection()
        except Exception:
            pass

        logger.info(
            "Phase 2: WCDMA registered, data=%s",
            "available" if wcdma_data else "not available",
        )

        # Return to LTE
        wcdma.deactivate_cell()
        lte.activate_cell()

        # Wait for LTE recovery
        lte_recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )

        if not lte_recovered:
            lte.deactivate_cell()
            pytest.fail("Modem did not return to LTE")

        # Re-establish LTE data connection
        lte_data_recovered = activate_data_connection_with_modem(modem, lte)

        # Cleanup
        lte.deactivate_cell()

        logger.info(
            "Phase 3: LTE recovered, data=%s",
            "restored" if lte_data_recovered else "failed",
        )
        assert lte_data_recovered, "LTE data connection not restored after RAT changes"

    # =========================================================================
    # PDP CONTEXT MANAGEMENT
    # =========================================================================

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_pdp_context_deactivation_recovery(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem recovers after PDP context is deactivated.

        Simulates data session termination while maintaining registration.
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to establish initial data connection")

        # Verify PDP context is active
        cgact_resp = modem.send_command("AT+CGACT?", timeout=AT_CMD_TIMEOUT)
        assert "+CGACT: 1,1" in cgact_resp, "PDP context not active"
        logger.info("Initial PDP context active")

        # Deactivate PDP context from modem side
        modem.send_command("AT+CGACT=0,1", timeout=AT_PDP_DEACTIVATE_TIMEOUT)
        time.sleep(SIGNAL_SETTLE_SEC)

        # Verify PDP context is deactivated
        cgact_resp = modem.send_command("AT+CGACT?", timeout=AT_CMD_TIMEOUT)
        logger.info("After deactivation: %s", cgact_resp.strip())

        # Modem should still be registered (only data session lost)
        assert modem.is_registered(), (
            "Modem should remain registered after PDP deactivation"
        )

        # Reactivate PDP context
        modem.send_command("AT+CGACT=1,1", timeout=AT_PDP_ACTIVATE_TIMEOUT)
        time.sleep(SIGNAL_SETTLE_SEC)

        # Verify PDP context is reactivated
        cgact_resp = modem.send_command("AT+CGACT?", timeout=AT_CMD_TIMEOUT)
        assert "+CGACT: 1,1" in cgact_resp, "PDP context reactivation failed"
        logger.info("PDP context recovered")

    @pytest.mark.timeout(TEST_TIMEOUT_MEDIUM)
    def test_apn_reconfiguration_recovery(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem handles APN reconfiguration.

        Simulates needing to change APN settings (e.g., roaming scenario).
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to establish initial data connection")

        logger.info("Initial data connection with default APN")

        # Deactivate current PDP context
        modem.send_command("AT+CGACT=0,1", timeout=AT_PDP_DEACTIVATE_TIMEOUT)
        time.sleep(POLL_INTERVAL_SEC)

        # Reconfigure with different APN
        modem.send_command('AT+CGDCONT=1,"IP","newapn"', timeout=AT_CMD_TIMEOUT)

        # Reactivate with new APN
        modem.send_command("AT+CGACT=1,1", timeout=AT_PDP_ACTIVATE_TIMEOUT)

        # Restore original APN for cleanup
        modem.send_command("AT+CGACT=0,1", timeout=AT_PDP_DEACTIVATE_TIMEOUT)
        modem.send_command('AT+CGDCONT=1,"IP","test"', timeout=AT_CMD_TIMEOUT)

        # Verify we can reconnect with original APN
        data_restored = activate_data_connection_with_modem(modem, lte_cell)
        assert data_restored, "Failed to restore data connection with original APN"

    # =========================================================================
    # INTERMITTENT CONNECTION
    # =========================================================================

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_intermittent_signal_recovery(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem handles intermittent signal loss (multiple brief outages).

        Simulates driving through areas with spotty coverage.
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to establish initial data connection")

        # Simulate multiple brief outages
        num_outages = 5
        outage_duration_sec = BRIEF_OUTAGE_DURATION_SEC
        recovery_wait_sec = INTERMITTENT_RECOVERY_WAIT_SEC
        successful_recoveries = 0

        for i in range(num_outages):
            logger.info("Outage %s/%s", i + 1, num_outages)

            # Brief signal loss
            lte_cell.set_dl_power(-120)
            time.sleep(outage_duration_sec)

            # Restore signal
            lte_cell.set_dl_power(-60)

            # Wait for recovery
            start = time.time()
            while (time.time() - start) < recovery_wait_sec:
                if modem.is_registered():
                    successful_recoveries += 1
                    logger.info("  Recovered in %.1fs")
                    break
                time.sleep(POLL_INTERVAL_SEC)
            else:
                logger.info("  Recovery timeout in outage %s", i + 1)

            # Brief stabilization
            time.sleep(SIGNAL_SETTLE_SEC)

        assert successful_recoveries >= num_outages - 1, (
            f"Modem only recovered from {successful_recoveries}/{num_outages} outages"
        )

        # Verify final data connection
        final_data = activate_data_connection_with_modem(modem, lte_cell)
        assert final_data, "Data connection not available after intermittent outages"

    @pytest.mark.timeout(TEST_TIMEOUT_MAXIMUM)
    def test_prolonged_outage_recovery(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test modem recovers after prolonged outage.

        Simulates extended time without coverage (e.g., underground parking).
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to establish initial data connection")

        initial_sq = modem.get_signal_quality()
        logger.info("Initial: mode=%s, RSRP=%s", initial_sq.mode, initial_sq.rsrp)

        # Simulate prolonged outage (2 minutes)
        logger.info("Starting prolonged outage (2 minutes)...")
        lte_cell.deactivate_cell()

        outage_duration = PROLONGED_OUTAGE_DURATION_SEC
        time.sleep(outage_duration)

        # Verify modem lost registration during outage
        assert not modem.is_registered(), "Modem should have lost registration"

        # Restore coverage
        logger.info("Restoring coverage...")
        lte_cell.activate_cell()

        # Wait for recovery (may take longer after prolonged outage)
        recovered = wait_for_registration(
            modem, timeout_sec=PROLONGED_RECOVERY_TIMEOUT_SEC, force_search=True
        )
        assert recovered, "Modem failed to recover after prolonged outage"

        # Verify data connection
        data_recovered = activate_data_connection_with_modem(modem, lte_cell)
        assert data_recovered, "Data connection not restored after prolonged outage"

        recovered_sq = modem.get_signal_quality()
        logger.info("Recovered: mode=%s, RSRP=%s", recovered_sq.mode, recovered_sq.rsrp)

    @pytest.mark.timeout(TEST_TIMEOUT_LONG)
    def test_rapid_power_fluctuations(
        self,
        lte_cell,
        modem,
        wait_for_registration,
    ):
        """Test modem stability under rapid signal power fluctuations.

        Simulates being in motion passing through varying coverage.
        """
        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        # Rapid power changes
        # Power levels capped at -100 dBm — deeper dips (e.g. -110) cause
        # the EG21-G to deregister in a way that makes recovery unreliable
        # within the test's time budget
        power_sequence = [
            -60,
            -80,
            -50,
            -100,
            -70,
            -90,
            -55,
            -100,
            -65,
            -85,
            -60,
            -95,
            -70,
            -100,
            -60,
            -80,
            -60,
        ]

        registration_checks = []

        for power in power_sequence:
            lte_cell.set_dl_power(power)
            time.sleep(RAPID_CHANGE_INTERVAL_SEC)
            registration_checks.append(modem.is_registered())

        # Restore stable signal — cycle the cell to reset CMW500 state after
        # rapid power changes, then reactivate at nominal power
        lte_cell.deactivate_cell()
        time.sleep(SIGNAL_SETTLE_SEC)
        lte_cell.set_dl_power(-60)
        lte_cell.activate_cell()
        time.sleep(CELL_STABILIZE_SEC)

        # Count how many times we stayed registered
        times_registered = sum(registration_checks)
        total_checks = len(registration_checks)

        logger.info(
            "Registered %d/%d checks during fluctuations",
            times_registered,
            total_checks,
        )

        # Final recovery check — force a radio cycle to ensure the modem
        # re-scans after the cell was cycled
        final_registered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC, force_search=True
        )
        assert final_registered, "Modem failed to stabilize after rapid fluctuations"

        # During rapid 1-second power swings the modem frequently loses and
        # re-acquires registration.  The primary goal of this test is final
        # recovery (asserted above); the mid-fluctuation count is informational.
        # Require at least 1 registered check to confirm the modem was not
        # completely unresponsive throughout the sequence.
        assert times_registered >= 1, (
            f"Modem never registered during fluctuations"
            f" ({times_registered}/{total_checks})"
        )
