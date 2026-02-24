"""
Pytest configuration and hooks for CMW500 modem testing.

Fixtures are organized in tests/fixtures/ modules and loaded via pytest_plugins.
"""

import pytest

# Load fixtures from organized modules
pytest_plugins = [
    "tests.fixtures.config",
    "tests.fixtures.cmw500",
    "tests.fixtures.dau",
    "tests.fixtures.modem",
    "tests.fixtures.helpers",
    "tests.fixtures.logic_mso",
    "tests.fixtures.data_traffic",
]


# =============================================================================
# PYTEST CONFIGURATION
# =============================================================================


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--cmw500-ip",
        action="store",
        default="172.22.1.4",
        help="CMW500 IP address",
    )
    parser.addoption(
        "--cmw500-config",
        action="store",
        default=None,
        help="Path to CMW500 YAML config file",
    )
    parser.addoption(
        "--modem-port",
        action="store",
        default=None,
        help="Modem serial port (auto-detect if not specified)",
    )
    parser.addoption(
        "--skip-modem",
        action="store_true",
        default=False,
        help="Skip tests requiring modem hardware",
    )
    parser.addoption(
        "--aws-endpoint",
        action="store",
        default=None,
        help="AWS test server URL for end-to-end tests",
    )
    parser.addoption(
        "--skip-end-to-end",
        action="store_true",
        default=False,
        help="Skip end-to-end internet connectivity tests",
    )
    parser.addoption(
        "--dau-lan-mode",
        action="store",
        default=None,
        choices=["dhcp", "static", "standalone"],
        help="DAU LAN interface mode (default: dhcp)",
    )
    parser.addoption(
        "--dau-lan-ip",
        action="store",
        default=None,
        help="DAU LAN static IP (implies --dau-lan-mode=static)",
    )
    parser.addoption(
        "--logic-mso-serial",
        action="store",
        default=None,
        help="Saleae Logic MSO serial number (auto-detect if not specified)",
    )
    parser.addoption(
        "--shunt-resistance",
        action="store",
        default=None,
        help="Current shunt resistance in Ohms (default: 0.01)",
    )
    parser.addoption(
        "--capture-duration",
        action="store",
        default=None,
        help="Power capture duration in seconds (default: 5.0)",
    )
    parser.addoption(
        "--power-mode",
        action="store",
        default=None,
        choices=["differential", "inamp"],
        help="Power measurement mode: differential (2-ch) or inamp (1-ch with amp)",
    )
    parser.addoption(
        "--inamp-gain",
        action="store",
        default=None,
        help="Instrumentation amplifier gain in V/V (default: 20.0, inamp mode only)",
    )
    parser.addoption(
        "--skip-power",
        action="store_true",
        default=False,
        help="Skip power consumption tests",
    )


def pytest_collection_modifyitems(config, items):
    """Skip hardware/end-to-end tests if specified."""
    if config.getoption("--skip-modem"):
        skip_hw = pytest.mark.skip(reason="--skip-modem specified")
        for item in items:
            if "hardware" in item.keywords:
                item.add_marker(skip_hw)

    if config.getoption("--skip-end-to-end"):
        skip_e2e = pytest.mark.skip(reason="--skip-end-to-end specified")
        for item in items:
            if "end_to_end" in item.keywords:
                item.add_marker(skip_e2e)

    if config.getoption("--skip-power"):
        skip_power = pytest.mark.skip(reason="--skip-power specified")
        for item in items:
            if "power_consumption" in item.keywords:
                item.add_marker(skip_power)
