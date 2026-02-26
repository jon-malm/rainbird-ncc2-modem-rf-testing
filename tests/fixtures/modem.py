"""Modem manager fixtures."""

import re

import pytest

from modem_interface import EG21GModemManager
from tests.constants import AT_CMD_TIMEOUT


@pytest.fixture(scope="session")
def modem_manager(request, modem_port):
    """
    Session-scoped modem manager. Skips if modem not available.

    Attempts to connect to the modem once at the start of the session.
    If connection fails, all tests using this fixture will be skipped.

    Backend is selected via ``--modem-backend``:
    - ``eg21g`` (default): direct serial via EG21GModemManager
    - ``h7``: eRPC via STM32H7 board using H7ModemManager
    """
    backend = request.config.getoption("--modem-backend")

    if backend == "h7":
        from modem_interface import H7ModemManager

        h7_host = request.config.getoption("--h7-host")
        h7_port = int(request.config.getoption("--h7-port"))
        modem = H7ModemManager(host=h7_host, erpc_port=h7_port)
    else:
        modem = EG21GModemManager()

    try:
        if modem_port and backend != "h7":
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

    Resets the modem to a clean state for each test:
    - Network scan mode set to LTE only so the modem doesn't waste time
      scanning WCDMA/GSM frequencies after a RAT-change test.

    NOTE: This fixture intentionally does NOT send AT+CFUN=1, AT+COPS=0,
    or cycle the radio.  The ``lte_cell`` fixture (which activates the
    CMW500 cell) runs concurrently with this fixture during pytest setup,
    so turning on the radio or triggering a network search here would race
    with cell activation — the modem would scan before the cell is active,
    waste its fast-scan window, and enter a long backoff.

    The ``wait_for_registration`` helper handles COPS=0, CFUN cycling,
    and registration polling only when the modem is actually unregistered
    and the cell is confirmed active.
    """
    # Reset scan mode to LTE only — previous WCDMA/GSM tests may have
    # changed this, preventing the modem from finding the LTE cell.
    # Use mode 3 (LTE only) rather than 0 (AUTO) so the modem doesn't
    # waste time scanning non-LTE frequencies on our LTE-only test cell.
    modem_manager.send_command(
        'AT+QCFG="nwscanmode",3', timeout=AT_CMD_TIMEOUT
    )

    # If the modem radio is on but NOT registered (left by a previous test
    # that deactivated its cell without turning the radio off), turn the
    # radio off now to prevent the scan-into-void / backoff problem.
    # If it IS registered, leave it alone — the previous lte_cell is still
    # active or the modem found a cell on its own.
    resp = modem_manager.send_command("AT+CEREG?")
    match = re.search(r"\+CEREG:\s*\d+,(\d+)", resp)
    if match and int(match.group(1)) not in (1, 5):
        # Not registered — check if radio is on
        cfun_resp = modem_manager.send_command("AT+CFUN?")
        if "+CFUN: 1" in cfun_resp:
            # Radio is on but no cell — turn it off to prevent backoff
            modem_manager.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)

    yield modem_manager
