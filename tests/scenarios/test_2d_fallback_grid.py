"""
2D fallback grid scenario tests.

The design documents specify a two-dimensional fallback strategy:
  - Horizontal axis: exhaust all cells at the current RAT before
    stepping down.
  - Vertical axis: step to the next lower RAT only after all cells at
    the current RAT have been tried.

These tests validate the vertical transitions: cell exhaustion at one
RAT triggering mode fallback, and recovery back to a higher RAT when a
cell becomes available again.
"""

import logging
import re
import time

import pytest

from tests.constants import (
    AT_CMD_TIMEOUT,
    CELL_STABILIZE_SEC,
    POLL_INTERVAL_SEC,
    RADIO_OFF_SETTLE_SEC,
    RADIO_ON_SETTLE_SEC,
    RAT_DETECTION_WAIT_SEC,
    RECOVERY_TIMEOUT_SEC,
    TEST_TIMEOUT_CARRIER_SWITCHOVER,
)
from tests.helpers import safe_cleanup

logger = logging.getLogger(__name__)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.wcdma
@pytest.mark.slow
class TestTwoDimensionalFallback:
    """Validate the 2D cell-then-RAT fallback grid."""

    @pytest.mark.timeout(TEST_TIMEOUT_CARRIER_SWITCHOVER)
    def test_exhaust_carriers_then_step_rat(
        self,
        carrier_cells,
        cmw500,
        modem,
        wait_for_registration,
    ):
        """Deactivating all LTE cells must cause RAT fallback to WCDMA.

        With both LTE cells removed, the only remaining cell is WCDMA.
        This validates the vertical axis: cell exhaustion at one RAT
        triggers mode fallback.
        """
        from equipment_cmw500.signaling.wcdma import WCDMACellConfig

        primary = carrier_cells["primary"]
        fallback = carrier_cells["fallback"]

        # Configure a WCDMA backstop cell (inactive initially — the modem
        # should only land here after both LTE cells are gone)
        wcdma = cmw500.get_wcdma_signaling()
        try:
            wcdma.configure_cell(WCDMACellConfig(dl_power_dbm=-60.0))
        except Exception as e:
            pytest.skip(f"Failed to configure WCDMA cell: {e}")

        # Ensure modem is on LTE
        assert wait_for_registration(modem), "Modem did not register on LTE"
        sq = modem.get_signal_quality()
        assert sq.mode == "LTE", f"Expected LTE, got {sq.mode}"
        logger.info("Phase 1: Registered on LTE")

        # Switch to AUTO scan mode and turn the radio OFF so the modem
        # cleanly releases its LTE bearer before we remove the cells.
        modem.send_command('AT+QCFG="nwscanmode",0', timeout=AT_CMD_TIMEOUT)
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)

        # Now swap cells while the radio is off
        primary.deactivate_cell()
        fallback.deactivate_cell()
        wcdma.activate_cell()
        time.sleep(CELL_STABILIZE_SEC)

        # Turn radio on — modem will scan and find WCDMA
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RAT_DETECTION_WAIT_SEC)

        # Wait for WCDMA registration (CREG for 3G)
        start = time.time()
        wcdma_registered = False
        while (time.time() - start) < RECOVERY_TIMEOUT_SEC:
            resp = modem.send_command("AT+CREG?")
            match = re.search(r"\+CREG:\s*\d+,(\d+)", resp)
            if match and int(match.group(1)) in (1, 5):
                wcdma_registered = True
                break
            time.sleep(POLL_INTERVAL_SEC)

        # Cleanup: always restore LTE scan mode and tear down WCDMA
        modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
        safe_cleanup(wcdma.deactivate_cell)

        assert wcdma_registered, (
            "Modem did not fall back to WCDMA after all LTE cells removed"
        )
        logger.info("Phase 2: Fell back to WCDMA after LTE cell exhaustion")

    @pytest.mark.timeout(TEST_TIMEOUT_CARRIER_SWITCHOVER)
    def test_carrier_chain_resets_on_mode_step(
        self,
        carrier_cells,
        cmw500,
        modem,
        wait_for_registration,
    ):
        """After RAT fallback to WCDMA, restoring an LTE cell recovers LTE.

        This validates that the carrier chain resets when returning to a
        higher RAT — the modem should not stay stuck on WCDMA.
        """
        from equipment_cmw500.signaling.wcdma import WCDMACellConfig

        primary = carrier_cells["primary"]
        fallback = carrier_cells["fallback"]

        wcdma = cmw500.get_wcdma_signaling()
        try:
            wcdma.configure_cell(WCDMACellConfig(dl_power_dbm=-60.0))
        except Exception as e:
            pytest.skip(f"Failed to configure WCDMA cell: {e}")

        # Phase 1: register on LTE
        if not wait_for_registration(modem):
            # Reset radio and retry — previous test may have left
            # the modem in AUTO scan mode
            modem.send_command(
                'AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT
            )
            modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
            time.sleep(RADIO_OFF_SETTLE_SEC)
            modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
            time.sleep(RADIO_ON_SETTLE_SEC)
            assert wait_for_registration(modem), (
                "Modem did not register on LTE"
            )
        logger.info("Phase 1: Registered on LTE")

        # Phase 2: remove both LTE cells, fall back to WCDMA
        primary.deactivate_cell()
        fallback.deactivate_cell()
        time.sleep(CELL_STABILIZE_SEC)

        modem.send_command('AT+QCFG="nwscanmode",0', timeout=AT_CMD_TIMEOUT)
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
            modem.send_command(
                'AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT
            )
            safe_cleanup(wcdma.deactivate_cell)
            pytest.skip("Modem did not fall back to WCDMA (prerequisite)")

        logger.info("Phase 2: On WCDMA")

        # Phase 3: restore an LTE cell and switch scan mode back to LTE
        modem.send_command('AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT)
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        wcdma.deactivate_cell()
        primary.activate_cell()
        time.sleep(CELL_STABILIZE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        # Wait for LTE re-registration
        lte_recovered = wait_for_registration(
            modem, timeout_sec=RECOVERY_TIMEOUT_SEC
        )

        assert lte_recovered, (
            "Modem did not recover to LTE after WCDMA fallback"
        )

        sq = modem.get_signal_quality()
        logger.info("Phase 3: Recovered to %s (RSRP=%s)", sq.mode, sq.rsrp)
        assert sq.mode == "LTE", (
            f"Expected LTE after carrier chain reset, got {sq.mode}"
        )
