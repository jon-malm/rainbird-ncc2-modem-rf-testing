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
