"""Modem manager fixtures (requires rainbird-ncc2-modem-poc)."""

import re
import sys
import time
from pathlib import Path

import pytest

from tests.constants import AT_CMD_TIMEOUT, RADIO_OFF_SETTLE_SEC, RADIO_ON_SETTLE_SEC


@pytest.fixture(scope="session")
def modem_manager(modem_port):
    """
    Session-scoped modem manager. Skips if modem not available.

    Attempts to connect to the modem once at the start of the session.
    If connection fails, all tests using this fixture will be skipped.
    """
    modem_poc_path = Path(__file__).parent.parent.parent / "modem-manager-eg21"
    if str(modem_poc_path) not in sys.path:
        sys.path.insert(0, str(modem_poc_path))

    try:
        from modem_manager import ModemManager
    except ImportError as e:
        pytest.skip(f"Modem manager module not available: {e}")

    modem = ModemManager()

    try:
        if modem_port:
            connected = modem.connect(modem_port)
        else:
            connected = modem.connect()
    except Exception as e:
        pytest.skip(f"Modem connection failed: {e}")

    if not connected:
        pytest.skip("Modem not available")

    yield modem

    modem.disconnect()


@pytest.fixture(scope="function")
def modem(modem_manager):
    """Function-scoped modem fixture.

    Ensures modem is in full functionality mode and triggers a network
    search if not currently registered.
    """
    # Check if modem is already registered
    resp = modem_manager.send_command("AT+CEREG?")
    match = re.search(r"\+CEREG:\s*\d+,(\d+)", resp)
    is_registered = match and int(match.group(1)) in (1, 5)

    if not is_registered:
        # Cycle radio to trigger fresh network search
        modem_manager.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem_manager.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)
    else:
        # Just ensure full functionality mode
        modem_manager.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)

    yield modem_manager
