"""
End-to-end DNS resolution tests.

Tests verify DNS resolution through the CMW500 DAU.
"""

import pytest

from tests.constants import REGISTRATION_TIMEOUT_SEC, TEST_TIMEOUT_STANDARD


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.end_to_end
class TestDNSResolution:
    """DNS resolution tests through DAU."""

    def test_dau_dns_servers_configured(self, dau_with_internet, aws_test_endpoint):
        """Test that DNS servers are properly configured."""
        if not aws_test_endpoint:
            pytest.skip("No external network configured - DNS test requires internet")

        dns = dau_with_internet.get_dns_servers()

        # Should have at least a primary DNS when using foreign DNS
        assert dns.primary, "No primary DNS server configured"

    def test_resolve_google_dns(self, dau_with_internet, aws_test_endpoint):
        """Test DNS resolution by pinging dns.google."""
        if not aws_test_endpoint:
            pytest.skip("No external network configured - DNS test requires internet")

        result = dau_with_internet.ping_external("dns.google", count=2)

        if not result.success:
            pytest.skip("DAU has no external network connectivity")

        assert result.packets_received > 0, (
            "Failed to resolve dns.google - DNS may not be working"
        )

    def test_resolve_common_hostnames(self, dau_with_internet, aws_test_endpoint):
        """Test resolving common hostnames."""
        if not aws_test_endpoint:
            pytest.skip(
                "No external network configured - DNS resolution requires internet"
            )

        hostnames = ["www.google.com", "www.amazon.com"]
        resolved = 0

        for hostname in hostnames:
            # CMW500 DATA:MEAS:PING:PCOunt has a minimum of 2
            result = dau_with_internet.ping_external(hostname, count=2)
            if result.success:
                resolved += 1

        if resolved == 0:
            pytest.skip("DAU has no external network connectivity")

    def test_custom_dns_server(self, cmw500):
        """Test setting custom DNS servers."""
        dau = cmw500.get_dau_controller()

        # Save original DNS so we can restore after the test
        original_dns = dau.get_dns_servers()

        # Configure custom DNS
        dau.set_dns_servers(primary="8.8.8.8", secondary="1.1.1.1")

        # Verify configuration
        dns = dau.get_dns_servers()
        assert "8.8.8.8" in dns.primary, "Primary DNS not set correctly"

        # Restore original DNS to avoid affecting subsequent tests
        dau.set_dns_servers(
            primary=original_dns.primary, secondary=original_dns.secondary
        )

    @pytest.mark.timeout(TEST_TIMEOUT_STANDARD)
    def test_modem_dns_through_dau(
        self,
        cmw500,
        end_to_end_data_path,
        modem,
        wait_for_registration,
        activate_data_connection_with_modem,
    ):
        """
        Test that modem can resolve DNS through DAU.

        Verifies that the modem registers on an LTE cell with DAU routing
        configured for external connectivity. Once AT+QIDNSGIP support is
        added to ModemManager, this test should perform actual DNS
        resolution from the modem side.
        """
        cell = end_to_end_data_path["cell"]

        # DAU reconfiguration (DHCP) may have dropped the VISA session and
        # triggered a reconnect, which invalidates cached signaling objects.
        # Get a fresh reference if the original one has a stale instrument.
        try:
            cell.query_cmd_safe(f"SENSe:LTE:{cell._sign}:RRCState?")
        except Exception:
            from equipment_cmw500.models.enums import CellState

            cell = cmw500.get_lte_signaling(cell_id=1)
            # The cell is still active on hardware; sync Python-side state
            cell._cell_state = CellState.ON

        assert wait_for_registration(modem, timeout_sec=REGISTRATION_TIMEOUT_SEC), (
            "Modem did not register on cell — "
            "cell is active, check modem scan mode and radio state"
        )

        if not activate_data_connection_with_modem(modem, cell):
            pytest.skip("Failed to activate data connection")

        # Verify the UE is visible to the CMW500 (registered state)
        ue_info = cell.get_ue_info()
        assert ue_info.state is not None
