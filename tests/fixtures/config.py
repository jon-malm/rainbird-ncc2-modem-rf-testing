"""Configuration fixtures for CMW500 and modem testing."""

import os
from pathlib import Path

import pytest
from equipment_cmw500 import CMW500Config, ConfigLoader


@pytest.fixture(scope="session")
def cmw500_ip(request) -> str:
    """Get CMW500 IP address from command line or environment."""
    return request.config.getoption("--cmw500-ip") or os.environ.get(
        "CMW500_IP", "172.22.1.4"
    )


@pytest.fixture(scope="session")
def aws_test_endpoint(request) -> str | None:
    """Get AWS test endpoint from command line or environment."""
    return request.config.getoption("--aws-endpoint") or os.environ.get(
        "CMW500_TEST_ENDPOINT", "3.151.226.42"
    )


@pytest.fixture(scope="session")
def cmw500_config(request, cmw500_ip) -> CMW500Config:
    """Load CMW500 configuration."""
    config_path = request.config.getoption("--cmw500-config")

    if config_path:
        loader = ConfigLoader(Path(config_path))
    else:
        loader = ConfigLoader()

    config = loader.load()

    # Override with command-line IP if provided
    config.connection.resource_name = f"TCPIP::{cmw500_ip}::hislip0::INSTR"

    # Apply DAU CLI overrides
    dau_lan_ip = request.config.getoption("--dau-lan-ip") or os.environ.get(
        "CMW500_DAU_LAN_IP"
    )
    dau_lan_mode = request.config.getoption("--dau-lan-mode") or os.environ.get(
        "CMW500_DAU_LAN_MODE"
    )

    if dau_lan_ip:
        config.dau.lan_dau_ip = dau_lan_ip
        # --dau-lan-ip implies static mode unless explicitly overridden
        if not dau_lan_mode:
            dau_lan_mode = "static"

    if dau_lan_mode:
        config.dau.lan_dau_mode = dau_lan_mode

    return config


@pytest.fixture(scope="session")
def modem_port(request) -> str | None:
    """Get modem port from command line or environment."""
    return request.config.getoption("--modem-port") or os.environ.get("MODEM_PORT")
