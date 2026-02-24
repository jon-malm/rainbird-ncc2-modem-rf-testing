"""
Data throughput measurement tests.

Tests verify data throughput through CMW500.

Note: LTE throughput measurement via the signaling application requires
active IP traffic (e.g., iperf3) through the DAU. The measure_throughput()
method raises NotImplementedError to indicate this — use DAU-based iperf3
testing for actual throughput measurements.
"""

import logging

import pytest

from tests.constants import (
    REGISTRATION_TIMEOUT_SEC,
    TEST_TIMEOUT_EXTENDED,
    TEST_TIMEOUT_STANDARD,
)
from tests.helpers import safe_cleanup

logger = logging.getLogger(__name__)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.slow
class TestDataThroughput:
    """Data throughput measurement tests."""

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_throughput_measurement_not_implemented(
        self,
        lte_cell,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test that throughput measurement raises NotImplementedError.

        Throughput measurement requires active IP traffic via DAU (iperf3),
        not a passive signaling-level query.
        """
        assert wait_for_registration(modem), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to activate data connection")

        with pytest.raises(NotImplementedError):
            lte_cell.measure_throughput(duration_sec=10)

    @pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
    def test_throughput_with_different_bandwidths(
        self, cmw500, modem, wait_for_registration, activate_data_connection_with_modem
    ):
        """Test cell activation with different LTE bandwidths.

        Verifies that cells can be configured and activated at different
        bandwidths. Actual throughput measurement requires DAU + iperf3.
        """
        from equipment_cmw500 import LTECellConfig
        from equipment_cmw500.models.enums import LTEBandwidth

        # Ensure clean state before configuring cells at different bandwidths
        safe_cleanup(cmw500.deactivate_all_cells)
        safe_cleanup(cmw500.clear_errors)

        # Start with 10 MHz (known working), then try others
        bandwidths = [
            LTEBandwidth.BW_10_MHZ,
            LTEBandwidth.BW_5_MHZ,
            LTEBandwidth.BW_20_MHZ,
        ]

        succeeded = []
        failed = []

        for bw in bandwidths:
            # Ensure connection is ready and cells are off before each iteration
            if not cmw500.ensure_connection_ready():
                pytest.skip("CMW500 connection not available")
            safe_cleanup(cmw500.deactivate_all_cells)
            safe_cleanup(cmw500.clear_errors)

            lte = cmw500.get_lte_signaling()

            config = LTECellConfig(bandwidth=bw)
            try:
                lte.configure_cell(config)
                lte.activate_cell()
            except Exception as e:
                # Try recovery once
                if cmw500.ensure_connection_ready():
                    safe_cleanup(cmw500.deactivate_all_cells)
                    safe_cleanup(cmw500.clear_errors)
                    lte = cmw500.get_lte_signaling()
                    try:
                        lte.configure_cell(config)
                        lte.activate_cell()
                    except Exception as e2:
                        logger.warning("Failed to configure %s: %s", bw.name, e2)
                        failed.append(bw.name)
                        continue
                else:
                    logger.warning("Failed to configure %s: %s", bw.name, e)
                    failed.append(bw.name)
                    continue

            if not wait_for_registration(
                modem, timeout_sec=REGISTRATION_TIMEOUT_SEC, force_search=True
            ):
                safe_cleanup(lte.deactivate_cell)
                logger.warning("Modem did not register for %s", bw.name)
                failed.append(bw.name)
                continue

            if not activate_data_connection_with_modem(modem, lte):
                safe_cleanup(lte.deactivate_cell)
                logger.warning("Data connection failed for %s", bw.name)
                failed.append(bw.name)
                continue

            logger.info("%s: Cell active, data connection established", bw.name)
            succeeded.append(bw.name)

            safe_cleanup(lte.deactivate_cell)

        assert len(succeeded) >= 1, f"No bandwidths succeeded. Failed: {failed}"
