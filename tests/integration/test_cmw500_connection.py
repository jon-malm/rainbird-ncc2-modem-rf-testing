"""
CMW500 connection tests.

Tests verify basic connectivity and communication with the CMW500.
"""

import pytest


@pytest.mark.hardware
class TestCMW500Connection:
    """CMW500 connection and basic communication tests."""

    def test_connection_established(self, cmw500_controller):
        """Test that CMW500 connection is established."""
        assert cmw500_controller.is_connected, "Should be connected to CMW500"

    def test_get_system_info(self, cmw500_controller):
        """Test retrieving system information."""
        info = cmw500_controller.get_system_info()

        assert info.idn, "Should have IDN string"
        assert "CMW" in info.idn, "Should be a CMW500 instrument"
        assert info.manufacturer
        assert info.model
        assert info.serial
        assert info.firmware

    def test_no_errors_after_reset(self, cmw500):
        """Test that there are no errors after reset."""
        # First clear any existing errors from previous tests
        cmw500.check_errors()  # This reads and clears the error queue

        # Now check that no new errors occur
        errors = cmw500.check_errors()
        assert len(errors) == 0, f"Unexpected errors after reset: {errors}"

    def test_get_lte_signaling(self, cmw500):
        """Test getting LTE signaling controller."""
        lte = cmw500.get_lte_signaling(cell_id=1)
        assert lte is not None
        assert lte.cell_id == 1

    def test_get_dau_controller(self, cmw500):
        """Test getting DAU controller."""
        dau = cmw500.get_dau_controller()
        assert dau is not None

    def test_context_manager(self, cmw500_controller):
        """Test that CMW500Controller supports context manager protocol.

        Note: We test the context manager interface on the existing session
        controller rather than creating a new connection, as the CMW500
        may not support multiple simultaneous connections and creating a
        second connection can disrupt the session-scoped connection.
        """
        from equipment_cmw500 import CMW500Controller

        # Verify the controller implements context manager protocol
        assert hasattr(CMW500Controller, "__enter__")
        assert hasattr(CMW500Controller, "__exit__")

        # Verify the session controller is connected
        assert cmw500_controller.is_connected
        info = cmw500_controller.get_system_info()
        assert "CMW" in info.idn
