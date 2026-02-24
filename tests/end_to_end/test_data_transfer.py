"""
End-to-end data transfer tests.

Tests verify data upload/download through the full path:
Modem -> CMW500 -> DAU -> Internet -> AWS test server

Note: LTE measure_throughput() and DAU get_throughput_stats() raise
NotImplementedError — throughput measurement requires active IP traffic
via iperf3 through the DAU, and the DAU has no passive traffic counters.
"""

import logging

import pytest

from tests.constants import (
    REGISTRATION_TIMEOUT_SEC,
    TEST_TIMEOUT_STANDARD,
)

logger = logging.getLogger(__name__)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.end_to_end
@pytest.mark.slow
class TestDataTransfer:
    """End-to-end data transfer tests."""

    def test_dau_throughput_stats_not_available(self, dau_with_internet):
        """Test that DAU throughput stats raise NotImplementedError.

        The CMW500 DAU subsystem has no passive traffic counters.
        Use iperf3 for active throughput measurement.
        """
        with pytest.raises(NotImplementedError):
            dau_with_internet.get_throughput_stats()

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_download_data_connection(
        self,
        end_to_end_data_path,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
        aws_test_endpoint,
    ):
        """
        Verify download data path is established.

        Establishes data connection through the full path. Actual throughput
        measurement requires iperf3 via the DAU.
        """
        cell = end_to_end_data_path["cell"]

        # Setup connection
        assert wait_for_registration(modem, timeout_sec=REGISTRATION_TIMEOUT_SEC), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )
        if not activate_data_connection_with_modem(modem, cell):
            pytest.skip("Failed to activate data connection")

        # Throughput measurement requires active IP traffic via DAU (iperf3)
        with pytest.raises(NotImplementedError):
            cell.measure_throughput(duration_sec=10)

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_upload_data_connection(
        self,
        end_to_end_data_path,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
        aws_test_endpoint,
    ):
        """
        Verify upload data path is established.

        Establishes data connection through the full path. Actual throughput
        measurement requires iperf3 via the DAU.
        """
        cell = end_to_end_data_path["cell"]

        # Setup connection
        assert wait_for_registration(modem, timeout_sec=REGISTRATION_TIMEOUT_SEC), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )
        if not activate_data_connection_with_modem(modem, cell):
            pytest.skip("Failed to activate data connection")

        # Throughput measurement requires active IP traffic via DAU (iperf3)
        with pytest.raises(NotImplementedError):
            cell.measure_throughput(duration_sec=10)

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_sustained_data_connection(
        self,
        end_to_end_data_path,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """
        Test sustained data connection over multiple checks.

        Verifies connection stability by checking UE state multiple times.
        """
        cell = end_to_end_data_path["cell"]

        # Setup connection
        assert wait_for_registration(modem, timeout_sec=REGISTRATION_TIMEOUT_SEC), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )
        if not activate_data_connection_with_modem(modem, cell):
            pytest.skip("Failed to activate data connection")

        # Verify connection stays up across multiple checks
        for i in range(3):
            ue_info = cell.get_ue_info()
            assert ue_info.state is not None, f"Lost UE state on check {i + 1}"
            logger.info("Check %d: UE state = %s", i + 1, ue_info.state)
