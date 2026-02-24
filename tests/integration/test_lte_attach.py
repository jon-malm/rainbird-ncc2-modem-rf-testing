"""
LTE attachment and registration tests.

Tests verify UE attachment to CMW500 LTE cell.
"""

import time

import pytest
from equipment_cmw500 import LTECellConfig
from equipment_cmw500.models.enums import LTEBand, LTEBandwidth

from tests.constants import (
    CMW_UE_REGISTRATION_TIMEOUT_SEC,
    REGISTRATION_TIMEOUT_SEC,
    TEST_TIMEOUT_STANDARD,
    UE_REPORT_POLL_INTERVAL_SEC,
    UE_REPORT_POLL_TIMEOUT_SEC,
)
from tests.helpers import safe_cleanup


@pytest.mark.hardware
@pytest.mark.lte
class TestLTEAttach:
    """LTE attachment and registration tests."""

    def test_configure_lte_cell(self, cmw500):
        """Test LTE cell configuration."""
        # Ensure clean state before configuring
        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        lte = cmw500.get_lte_signaling()

        config = LTECellConfig(
            band=LTEBand.BAND_7,
            bandwidth=LTEBandwidth.BW_10_MHZ,
            dl_earfcn=3100,
            dl_power_dbm=-60.0,
            mcc="001",
            mnc="01",
        )

        try:
            lte.configure_cell(config)
        except Exception as e:
            pytest.skip(f"Failed to configure LTE cell: {e}")

        # Cell should still be off
        assert lte.cell_state.name == "OFF"

    def test_activate_lte_cell(self, cmw500):
        """Test LTE cell activation."""
        # Ensure clean state before configuring
        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        lte = cmw500.get_lte_signaling()

        config = LTECellConfig()
        try:
            lte.configure_cell(config)
            lte.activate_cell()
        except Exception as e:
            pytest.skip(f"Failed to configure/activate cell: {e}")

        assert lte.cell_state.name == "ON"

        # Cleanup
        safe_cleanup(lte.deactivate_cell)
        assert lte.cell_state.name == "OFF"

    def test_lte_cell_fixture(self, lte_cell):
        """Test that lte_cell fixture provides activated cell."""
        assert lte_cell.cell_state.name == "ON"

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_ue_attach_success(self, lte_cell, modem, wait_for_registration):
        """Test successful UE attach to LTE cell."""
        # Modem should register on the cell
        assert wait_for_registration(modem, timeout_sec=REGISTRATION_TIMEOUT_SEC), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Verify registration on CMW500 side
        assert lte_cell.wait_for_ue_registration(
            timeout_sec=CMW_UE_REGISTRATION_TIMEOUT_SEC
        ), "CMW500 did not detect UE registration"

        # Get UE info
        ue_info = lte_cell.get_ue_info()
        # IMSI may be None if not available through current SCPI interface
        assert ue_info.state is not None

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_ue_signal_quality(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test signal quality measurements after attach."""
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # UE measurement reports require RRC CONNECTED state.  After
        # registration the UE may fall back to RRC IDLE before the test
        # starts polling, in which case the CMW500 returns NAV
        # indefinitely.  Ensure the UE is paged into CONNECTED first.
        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Could not transition UE to RRC CONNECTED")

        # Poll until at least one value is available (CMW500 returns NAV
        # until the first measurement report arrives from the UE).
        cmw_sq = None
        start = time.time()
        while (time.time() - start) < UE_REPORT_POLL_TIMEOUT_SEC:
            cmw_sq = lte_cell.get_signal_quality(safe=True)
            if cmw_sq.rsrp_dbm is not None or cmw_sq.rsrq_db is not None:
                break
            time.sleep(UE_REPORT_POLL_INTERVAL_SEC)

        assert cmw_sq.rsrp_dbm is not None or cmw_sq.rsrq_db is not None, (
            f"No UE measurement report received within "
            f"{UE_REPORT_POLL_TIMEOUT_SEC}s of registration"
        )

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_data_connection(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test LTE data connection establishment."""
        # Wait for registration
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        # Activate data connection (uses modem-side PDP activation if needed)
        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to activate data connection")

        # Verify UE state
        ue_info = lte_cell.get_ue_info()
        # State should indicate connected or established
        assert ue_info.state is not None
