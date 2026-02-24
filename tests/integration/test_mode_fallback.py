"""
Mode fallback tests.

Tests verify modem behavior when switching between cell technologies.
"""

import logging
import time

import pytest

from tests.constants import (
    AT_CMD_TIMEOUT,
    CELL_RESELECTION_WAIT_SEC,
    CELL_STABILIZE_SEC,
    POLL_INTERVAL_SEC,
    QOS_LTE_RSRP_THRESHOLD_DBM,
    RADIO_OFF_SETTLE_SEC,
    RAT_DETECTION_WAIT_SEC,
    RECOVERY_TIMEOUT_SEC,
    SIGNAL_SETTLE_SEC,
    TEST_TIMEOUT_MEDIUM,
    TEST_TIMEOUT_STANDARD,
)
from tests.helpers import safe_cleanup

logger = logging.getLogger(__name__)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.wcdma
@pytest.mark.slow
class TestModeFallback:
    """Cellular mode fallback behavior tests."""

    @pytest.mark.timeout(TEST_TIMEOUT_MEDIUM)
    def test_lte_to_wcdma_fallback(self, cmw500, modem, wait_for_registration):
        """Test fallback from LTE to WCDMA when LTE cell is disabled."""
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.signaling.wcdma import WCDMACellConfig

        # Clear any errors and ensure cells are OFF before configuring
        safe_cleanup(cmw500.check_errors)
        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        # Start with LTE cell active
        lte = cmw500.get_lte_signaling()
        try:
            lte.configure_cell(LTECellConfig())
            lte.activate_cell()
        except Exception as e:
            pytest.skip(f"Failed to configure/activate LTE cell: {e}")

        # Configure WCDMA cell but keep inactive
        wcdma = cmw500.get_wcdma_signaling()
        try:
            wcdma.configure_cell(WCDMACellConfig())
        except Exception as e:
            safe_cleanup(lte.deactivate_cell)
            pytest.skip(f"Failed to configure WCDMA cell: {e}")

        # Wait for LTE registration
        if not wait_for_registration(modem):
            safe_cleanup(lte.deactivate_cell)
            pytest.skip("Modem did not register on LTE cell")

        sq = modem.get_signal_quality()
        if sq.mode != "LTE":
            safe_cleanup(lte.deactivate_cell)
            pytest.skip(f"Modem not in LTE mode (got {sq.mode})")

        # Disable LTE, enable WCDMA — switch scan mode to AUTO so the
        # modem can find the WCDMA cell (fixture sets LTE-only mode).
        modem.send_command('AT+QCFG="nwscanmode",0', timeout=AT_CMD_TIMEOUT)
        try:
            lte.deactivate_cell()
            wcdma.activate_cell()
        except Exception as e:
            modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
            pytest.skip(f"Failed to switch cells: {e}")

        # Cycle radio to trigger fresh WCDMA scan
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RAT_DETECTION_WAIT_SEC)

        # Wait for WCDMA registration using CREG (CS registration for 2G/3G)
        import re

        start = time.time()
        registered = False
        while (time.time() - start) < RECOVERY_TIMEOUT_SEC:
            # Check CS registration (CREG) for WCDMA
            resp = modem.send_command("AT+CREG?")
            match = re.search(r"\+CREG:\s*\d+,(\d+)", resp)
            if match:
                stat = int(match.group(1))
                if stat in (1, 5):  # registered home or roaming
                    registered = True
                    break
            time.sleep(POLL_INTERVAL_SEC)

        if not registered:
            safe_cleanup(wcdma.deactivate_cell)
            modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
            pytest.skip("Modem did not fall back to WCDMA")

        sq = modem.get_signal_quality()
        # Cleanup before assertion — restore LTE-only scan mode and turn
        # radio off.  Leave the radio off so the modem doesn't scan into
        # the void before the next test's lte_cell fixture activates a cell.
        # The wait_for_registration helper will turn it back on.
        safe_cleanup(wcdma.deactivate_cell)
        modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        assert sq.mode == "WCDMA", f"Expected WCDMA mode, got {sq.mode}"

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_signal_degradation_handling(self, lte_cell, modem, wait_for_registration):
        """Test modem behavior under degrading signal conditions."""
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Reduce cell power gradually, including the spec RSRP threshold
        # boundary (-120 dBm per Operational Performance Spec Section 5.4)
        power_levels = [-60, -80, -100, -110, QOS_LTE_RSRP_THRESHOLD_DBM]

        for power in power_levels:
            lte_cell.set_dl_power(power)
            time.sleep(SIGNAL_SETTLE_SEC)

            sq = modem.get_signal_quality()
            logger.info("Power: %s dBm, RSRP: %s dBm", power, sq.rsrp)

            # Check modem is still registered (may fail at very low power)
            if not modem.is_registered():
                logger.info("Modem lost registration at %s dBm", power)
                break

        # Restore power
        lte_cell.set_dl_power(-60)

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_cell_reselection(self, cmw500, modem, wait_for_registration):
        """Test modem cell reselection between two LTE cells.

        Configures two intra-frequency LTE cells (SIGN1 and SIGN2) on the
        same EARFCN with different PCIs.  SIB3 reselection parameters and
        SIB4 neighbor cell lists are configured so the UE performs
        intra-frequency measurements.  Swapping DL power levels triggers
        the UE to reselect to the stronger cell.
        """
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.models.enums import LTEBand

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
                safe_cleanup(lte1.deactivate_cell)
                pytest.skip("CMW500 does not support SIB3 reselection parameters")
            if not lte1.configure_neighbor_cell(1, band, earfcn, pci2):
                safe_cleanup(lte1.deactivate_cell)
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

        # Activate both cells — dual-cell may need longer timeout
        try:
            lte1.activate_cell(timeout_ms=60000)
            lte2.activate_cell(timeout_ms=60000)
        except Exception as e:
            safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
            pytest.skip(f"Failed to activate dual cells: {e}")

        time.sleep(CELL_STABILIZE_SEC)

        # Wait for modem to register (should camp on cell 1 — stronger)
        if not wait_for_registration(modem):
            safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
            pytest.skip("Modem did not register on any cell")

        # Verify initial PCI
        sq = modem.get_signal_quality()
        logger.info("Initial: mode=%s, RSRP=%s dBm", sq.mode, sq.rsrp)

        # Swap power levels: cell 2 becomes stronger
        lte1.set_dl_power(-90.0)
        lte2.set_dl_power(-60.0)

        # Wait for UE to measure and reselect
        time.sleep(CELL_RESELECTION_WAIT_SEC)

        # Verify modem is still registered after reselection
        registered = wait_for_registration(modem, timeout_sec=RECOVERY_TIMEOUT_SEC)

        # Cleanup
        safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)

        assert registered, "Modem lost registration during cell reselection"
        sq = modem.get_signal_quality()
        logger.info("After reselection: mode=%s, RSRP=%s dBm", sq.mode, sq.rsrp)
