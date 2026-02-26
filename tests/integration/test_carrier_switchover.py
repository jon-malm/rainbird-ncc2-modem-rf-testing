"""
Carrier switchover integration tests via eSIM profile switching.

Tests verify that carrier switching uses the eSIM profile path
(AT+QESIM) rather than CPOL, ensuring home-network registration
instead of roaming deprioritization.

Scenarios covered:
- eSIM profile listing through ABC interface
- eSIM profile switch maintains RAT level
- Carrier fallback before RAT fallback (2D grid horizontal axis)
- Home registration (not roaming) after profile switch
"""

import logging
import re
import time

import pytest

from tests.constants import (
    AT_CMD_TIMEOUT,
    CARRIER_SWITCHOVER_TIMEOUT_SEC,
    CELL_STABILIZE_SEC,
    ESIM_SWITCH_SETTLE_SEC,
    POLL_INTERVAL_SEC,
    RADIO_OFF_SETTLE_SEC,
    RADIO_ON_SETTLE_SEC,
    TEST_TIMEOUT_CARRIER_SWITCHOVER,
)

logger = logging.getLogger(__name__)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.slow
class TestCarrierSwitchover:
    """Carrier-level switching via eSIM profile management."""

    @pytest.mark.timeout(TEST_TIMEOUT_CARRIER_SWITCHOVER)
    def test_esim_profile_list(self, modem):
        """Verify modem can list eSIM profiles through the ABC interface.

        Exercises modem.list_esim_profiles() to confirm the ABC plumbing
        works end-to-end.  Skips if eSIM is not supported.
        """
        profiles = modem.list_esim_profiles()
        if profiles is None:
            pytest.skip("eSIM not supported on this modem")

        assert isinstance(profiles, list)
        logger.info("Found %d eSIM profile(s)", len(profiles))

        for p in profiles:
            assert "iccid" in p, "Profile missing 'iccid' key"
            assert "status" in p, "Profile missing 'status' key"
            logger.info(
                "  ICCID=%s  status=%s  nickname=%s",
                p["iccid"],
                p["status"],
                p.get("nickname", ""),
            )

    @pytest.mark.timeout(TEST_TIMEOUT_CARRIER_SWITCHOVER)
    def test_esim_switch_maintains_rat(
        self,
        lte_cell,
        modem,
        wait_for_registration,
    ):
        """Switching eSIM profiles must not cause a RAT downgrade.

        After switching to an alternate profile the modem should remain
        on LTE (or re-register on LTE), not fall back to WCDMA/GSM.
        Requires 2+ installed eSIM profiles.
        """
        profiles = modem.list_esim_profiles()
        if profiles is None:
            pytest.skip("eSIM not supported on this modem")
        if len(profiles) < 2:
            pytest.skip(
                f"Need >=2 eSIM profiles to test switching (found {len(profiles)})"
            )

        # Ensure registered on LTE before switching
        assert wait_for_registration(modem), "Modem did not register on LTE cell"

        sq = modem.get_signal_quality()
        assert sq.mode == "LTE", f"Expected LTE before switch, got {sq.mode}"
        logger.info("Pre-switch: mode=%s RSRP=%s", sq.mode, sq.rsrp)

        # Record original ICCID for restore
        original_iccid = modem.get_active_iccid()
        logger.info("Original ICCID: %s", original_iccid)

        # Find an alternate profile
        alternate = next(
            (p for p in profiles if p["iccid"] != original_iccid),
            None,
        )
        if alternate is None:
            pytest.skip("No alternate profile found")

        # Switch to alternate
        switched = modem.switch_esim_profile(alternate["iccid"])
        assert switched, f"Failed to switch to profile {alternate['iccid']}"
        time.sleep(ESIM_SWITCH_SETTLE_SEC)
        logger.info("Switched to ICCID=%s", alternate["iccid"])

        # Wait for re-registration after profile switch
        registered = wait_for_registration(
            modem, timeout_sec=CARRIER_SWITCHOVER_TIMEOUT_SEC
        )

        # Restore original profile regardless of outcome
        modem.switch_esim_profile(original_iccid)
        time.sleep(ESIM_SWITCH_SETTLE_SEC)

        assert registered, "Modem did not re-register after eSIM profile switch"

        sq = modem.get_signal_quality()
        logger.info("Post-switch: mode=%s RSRP=%s", sq.mode, sq.rsrp)
        assert sq.mode == "LTE", (
            f"Modem fell back to {sq.mode} after eSIM switch — expected LTE"
        )

    @pytest.mark.timeout(TEST_TIMEOUT_CARRIER_SWITCHOVER)
    def test_carrier_fallback_before_rat_fallback(
        self,
        carrier_cells,
        modem,
        wait_for_registration,
    ):
        """Deactivating one LTE cell causes cell reselection, not RAT fallback.

        With two intra-frequency LTE cells, removing one should make the
        modem reselect to the remaining cell (still LTE) rather than
        stepping down to WCDMA.
        """
        primary = carrier_cells["primary"]

        # Ensure modem registers on either cell
        assert wait_for_registration(modem), "Modem did not register on any cell"

        sq = modem.get_signal_quality()
        assert sq.mode == "LTE", f"Expected LTE, got {sq.mode}"
        logger.info("Registered on LTE")

        # Deactivate primary cell — modem should find the fallback cell
        # via SIB4 intra-frequency neighbor info
        primary.deactivate_cell()
        time.sleep(CELL_STABILIZE_SEC)

        # Force radio cycle to speed up cell search
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        # Wait for re-registration on fallback cell
        start = time.time()
        recovered = False
        while (time.time() - start) < CARRIER_SWITCHOVER_TIMEOUT_SEC:
            resp = modem.send_command("AT+CEREG?")
            match = re.search(r"\+CEREG:\s*\d+,(\d+)", resp)
            if match and int(match.group(1)) in (1, 5):
                recovered = True
                break
            time.sleep(POLL_INTERVAL_SEC)

        assert recovered, "Modem did not re-register after primary cell loss"

        sq = modem.get_signal_quality()
        logger.info("After carrier fallback: mode=%s RSRP=%s", sq.mode, sq.rsrp)
        assert sq.mode == "LTE", (
            f"Modem fell back to {sq.mode} instead of reselecting LTE cell"
        )

    @pytest.mark.timeout(TEST_TIMEOUT_CARRIER_SWITCHOVER)
    def test_carrier_native_not_roaming(self, lte_cell, modem, wait_for_registration):
        """After eSIM profile switch, modem must show home registration (stat=1).

        CPOL-based carrier selection causes roaming (stat=5).  The eSIM
        approach should yield native/home registration.
        """
        profiles = modem.list_esim_profiles()
        if profiles is None:
            pytest.skip("eSIM not supported on this modem")
        if len(profiles) < 2:
            pytest.skip(
                f"Need >=2 eSIM profiles to test switching (found {len(profiles)})"
            )

        assert wait_for_registration(modem), "Modem did not register"

        original_iccid = modem.get_active_iccid()

        # Find alternate profile
        alternate = next(
            (p for p in profiles if p["iccid"] != original_iccid),
            None,
        )
        if alternate is None:
            pytest.skip("No alternate profile found")

        # Switch profile
        switched = modem.switch_esim_profile(alternate["iccid"])
        assert switched, f"Failed to switch to profile {alternate['iccid']}"
        time.sleep(ESIM_SWITCH_SETTLE_SEC)

        # Wait for re-registration
        registered = wait_for_registration(
            modem, timeout_sec=CARRIER_SWITCHOVER_TIMEOUT_SEC
        )

        # Check registration status via AT+COPS?
        cops_resp = modem.send_command("AT+COPS?", timeout=AT_CMD_TIMEOUT)
        logger.info("AT+COPS? after eSIM switch: %s", cops_resp.strip())

        # Also check CEREG for stat value
        cereg_resp = modem.send_command("AT+CEREG?", timeout=AT_CMD_TIMEOUT)
        logger.info("AT+CEREG? after eSIM switch: %s", cereg_resp.strip())

        # Restore original profile
        modem.switch_esim_profile(original_iccid)
        time.sleep(ESIM_SWITCH_SETTLE_SEC)

        assert registered, "Modem did not re-register after eSIM switch"

        # Parse CEREG stat — expect 1 (home) not 5 (roaming)
        cereg_match = re.search(r"\+CEREG:\s*\d+,(\d+)", cereg_resp)
        assert cereg_match, f"Could not parse CEREG response: {cereg_resp}"
        stat = int(cereg_match.group(1))
        assert stat == 1, (
            f"Expected home registration (stat=1) after eSIM switch, got stat={stat}. "
            f"stat=5 indicates roaming — eSIM switch may have fallen back to CPOL path."
        )
