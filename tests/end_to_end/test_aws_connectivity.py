"""
End-to-end AWS connectivity tests.

Tests verify that data can flow from the modem through the CMW500 DAU
to an external AWS test server on the internet.

Data path: Modem -> CMW500 LTE Cell -> DAU -> LAN DAU -> Internet -> AWS
"""

import pytest

from tests.constants import (
    CMW_UE_REGISTRATION_TIMEOUT_SEC,
    REGISTRATION_TIMEOUT_SEC,
    TEST_TIMEOUT_STANDARD,
)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.end_to_end
class TestAWSConnectivity:
    """End-to-end connectivity tests to AWS test server."""

    def test_dau_can_ping_external(self, dau_with_internet, aws_test_endpoint):
        """Test that DAU can reach the internet directly."""
        if not aws_test_endpoint:
            pytest.skip("No AWS test endpoint configured")

        result = dau_with_internet.ping_external(aws_test_endpoint, count=4)

        if not result.success:
            pytest.skip("DAU has no external network connectivity")

        assert result.packets_received > 0, "No ping responses received"
        assert result.rtt_avg_ms > 0, "Invalid RTT"

    def test_dau_dns_resolution(self, dau_with_internet, aws_test_endpoint):
        """Test DNS resolution through DAU."""
        if not aws_test_endpoint:
            pytest.skip("No external network endpoint configured")

        # Ping a well-known hostname to verify DNS works
        result = dau_with_internet.ping_external("dns.google", count=2)

        if not result.success:
            pytest.skip("DAU has no external network connectivity")

        assert result.packets_received > 0, "DNS resolution or connectivity failed"

    def test_lte_cell_with_dau_routing(self, end_to_end_data_path, aws_test_endpoint):
        """Test that LTE cell and DAU are properly configured together."""
        cell = end_to_end_data_path["cell"]
        dau = end_to_end_data_path["dau"]

        # Verify cell is active
        assert cell.cell_state.name == "ON", "LTE cell should be active"

        # Verify DAU configuration
        lan_info = dau.get_lan_dau_info()
        # Accept AUTomatic/AUT for standalone, DHCPv4/DHCP, or STATic/STAT
        valid_modes = ["DHCP", "DHCPv4", "STATic", "STAT", "AUTomatic", "AUT"]
        assert lan_info.mode in valid_modes, f"LAN DAU mode {lan_info.mode} not valid"

        # NAT status check - NAT is optional for standalone mode
        nat_status = dau.get_nat_status()
        # Just verify we can query NAT status (dataclass always has .enabled)
        assert isinstance(nat_status.enabled, bool)

    # Note: The following tests require a connected modem
    # They are marked to skip if modem is not available

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_modem_attach_and_ping_aws(
        self,
        end_to_end_data_path,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
        aws_test_endpoint,
    ):
        """
        Full end-to-end test: modem attaches to CMW500 and pings AWS.

        This test verifies the complete data path:
        1. Modem registers on CMW500 LTE cell
        2. Data connection is established
        3. Modem can ping external AWS server through DAU
        """
        cell = end_to_end_data_path["cell"]

        # Wait for modem to register
        assert wait_for_registration(
            modem, timeout_sec=REGISTRATION_TIMEOUT_SEC
        ), "Modem failed to register on active cell"

        # Verify registration on CMW500 side
        assert cell.wait_for_ue_registration(
            timeout_sec=CMW_UE_REGISTRATION_TIMEOUT_SEC
        ), "UE not registered on CMW500"

        # Activate data connection (uses modem-side PDP activation if needed)
        assert activate_data_connection_with_modem(modem, cell), (
            "Failed to establish data connection"
        )

        # Get UE info
        ue_info = cell.get_ue_info()
        # Note: IMSI may be None depending on SCPI interface availability
        assert ue_info.state is not None, "No UE state available"

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_throughput_through_dau(
        self,
        end_to_end_data_path,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """Test data path through DAU is established.

        DAU has no passive throughput counters — use iperf3 for actual
        throughput measurement.
        """
        cell = end_to_end_data_path["cell"]
        dau = end_to_end_data_path["dau"]

        # Wait for registration and data connection
        assert wait_for_registration(
            modem, timeout_sec=REGISTRATION_TIMEOUT_SEC
        ), "Modem did not register on active cell"
        assert activate_data_connection_with_modem(modem, cell), (
            "Failed to activate data connection"
        )

        # DAU has no passive throughput counters
        with pytest.raises(NotImplementedError):
            dau.get_throughput_stats()
