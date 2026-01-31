"""Helper fixtures for common test operations."""

import logging
import re
import time

import pytest

from tests.constants import (
    AT_CMD_TIMEOUT,
    AT_PDP_ACTIVATE_TIMEOUT,
    AT_PDP_DEACTIVATE_TIMEOUT,
    DATA_CONNECTION_TIMEOUT_SEC,
    DEREG_POLL_INTERVAL_SEC,
    DEREGISTRATION_TIMEOUT_SEC,
    POLL_INTERVAL_SEC,
    RADIO_OFF_SETTLE_SEC,
    RADIO_ON_SETTLE_SEC,
    REGISTRATION_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def wait_for_registration():
    """Helper fixture that waits for modem to register on LTE.

    Uses AT+CEREG? to check EPS (LTE) registration status rather than
    AT+CREG? which only checks CS (circuit-switched) registration.
    For LTE-only test cells, CEREG is the correct indicator.
    """

    def _wait(
        modem,
        timeout_sec: float = REGISTRATION_TIMEOUT_SEC,
        force_search: bool = False,
    ) -> bool:
        """
        Wait for modem to register on LTE network.

        Args:
            modem: ModemManager instance
            timeout_sec: Maximum time to wait for registration
            force_search: If True, trigger a fresh network search first

        Returns:
            True if registered successfully, False on timeout
        """
        if force_search:
            # Trigger fresh network search by cycling radio
            modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
            time.sleep(RADIO_OFF_SETTLE_SEC)
            modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
            time.sleep(RADIO_ON_SETTLE_SEC)

        start = time.time()

        while (time.time() - start) < timeout_sec:
            # Check EPS (LTE) registration status
            resp = modem.send_command("AT+CEREG?")
            match = re.search(r"\+CEREG:\s*\d+,(\d+)", resp)
            if match:
                stat = int(match.group(1))
                # 1 = registered home, 5 = registered roaming
                if stat in (1, 5):
                    return True
            time.sleep(POLL_INTERVAL_SEC)

        return False

    return _wait


@pytest.fixture
def activate_data_connection_with_modem():
    """Helper fixture that activates data connection from modem side.

    When the UE is in RRC IDLE state, the CMW500's paging action may not
    transition it to CONNECTED state. This fixture activates the PDP context
    from the modem side, which triggers uplink signaling and transitions
    the UE to RRC CONNECTED state.
    """

    def _activate(
        modem, cell, timeout_sec: float = DATA_CONNECTION_TIMEOUT_SEC
    ) -> bool:
        """
        Activate data connection, using modem-side PDP activation if needed.

        Args:
            modem: ModemManager instance
            cell: LTE cell signaling instance
            timeout_sec: Maximum time to wait for connection

        Returns:
            True if data connection established, False otherwise
        """
        # First try CMW500's activate_data_connection
        if cell.activate_data_connection(timeout_sec=10.0):
            logger.debug("Data connection activated via CMW500 paging")
            return True

        # CMW500 paging didn't work - UE is likely in RRC IDLE
        # Activate PDP context from modem side to trigger uplink signaling
        logger.info("CMW500 paging failed - activating PDP context from modem side")

        # Check current PDP context state
        cgact_resp = modem.send_command("AT+CGACT?", timeout=AT_CMD_TIMEOUT)
        logger.debug("Current CGACT state: %s", cgact_resp.replace("\n", " | "))

        # Ensure PDP context is configured for the test APN
        modem.send_command('AT+CGDCONT=1,"IP","test"', timeout=AT_CMD_TIMEOUT)

        # If PDP context 1 is already active, deactivate first then reactivate
        # This forces uplink signaling
        if "+CGACT: 1,1" in cgact_resp:
            logger.debug("PDP context 1 already active - cycling to trigger signaling")
            modem.send_command("AT+CGACT=0,1", timeout=AT_PDP_DEACTIVATE_TIMEOUT)
            time.sleep(RADIO_OFF_SETTLE_SEC)

        # Activate PDP context - this triggers uplink signaling.
        # If the modem just recovered from detach/power-off, it may not
        # be PS-attached yet, so ensure CGATT=1 and retry a few times.
        pdp_activated = False
        for attempt in range(3):
            # Ensure PS domain is attached before trying PDP activation
            cgatt = modem.send_command("AT+CGATT?", timeout=AT_CMD_TIMEOUT)
            if "+CGATT: 0" in cgatt:
                logger.debug("PS not attached, sending AT+CGATT=1")
                modem.send_command("AT+CGATT=1", timeout=AT_PDP_ACTIVATE_TIMEOUT)
                time.sleep(RADIO_ON_SETTLE_SEC)
            resp = modem.send_command("AT+CGACT=1,1", timeout=AT_PDP_ACTIVATE_TIMEOUT)
            if "OK" in resp and "ERROR" not in resp:
                pdp_activated = True
                break
            # Check if it's already active (ERROR because already active)
            cgact_check = modem.send_command("AT+CGACT?", timeout=AT_CMD_TIMEOUT)
            if "+CGACT: 1,1" in cgact_check:
                pdp_activated = True
                break
            logger.warning("PDP context activation failed: %s", resp)
            # Wait for registration before retrying
            time.sleep(RADIO_ON_SETTLE_SEC)

        if not pdp_activated:
            logger.warning("PDP activation failed after retries")
            return False

        # Wait briefly for RRC state to transition
        time.sleep(POLL_INTERVAL_SEC)

        # Now verify CMW500 sees the UE in CONNECTED state
        start = time.time()
        while (time.time() - start) < timeout_sec:
            if cell.activate_data_connection(timeout_sec=5.0):
                logger.debug("Data connection established after modem PDP activation")
                return True
            time.sleep(POLL_INTERVAL_SEC)

        # CMW500 still can't see the UE in CONNECTED state.  The PDP context
        # may be stale from a previous cell session (modem reports active but
        # the radio bearer is gone).  Force a full PDP cycle and retry once.
        logger.info("Retrying with forced PDP deactivation/reactivation")
        modem.send_command("AT+CGACT=0,1", timeout=AT_PDP_DEACTIVATE_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CGACT=1,1", timeout=AT_PDP_ACTIVATE_TIMEOUT)
        time.sleep(POLL_INTERVAL_SEC)

        if cell.activate_data_connection(timeout_sec=10.0):
            logger.debug("Data connection established after forced PDP cycle")
            return True

        # Last resort: cycle the radio to reset PS domain state.
        # The Quectel EG21-G sometimes fails to restore the PS data path
        # after network-initiated detach without a full CFUN cycle.
        logger.info("Retrying with CFUN cycle to reset PS domain")
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)
        # Re-attach and activate PDP
        modem.send_command("AT+CGATT=1", timeout=AT_PDP_ACTIVATE_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)
        modem.send_command("AT+CGACT=1,1", timeout=AT_PDP_ACTIVATE_TIMEOUT)
        time.sleep(POLL_INTERVAL_SEC)

        if cell.activate_data_connection(timeout_sec=10.0):
            logger.debug("Data connection established after CFUN cycle")
            return True

        logger.warning("Data connection not established after all recovery attempts")
        return False

    return _activate


@pytest.fixture
def measure_signal_quality():
    """Helper fixture to measure signal quality multiple times."""

    def _measure(modem, count: int = 5, interval_sec: float = 1.0) -> list[dict]:
        measurements = []

        for _ in range(count):
            sq = modem.get_signal_quality()
            measurements.append(
                {
                    "mode": sq.mode,
                    "rssi": sq.rssi,
                    "rsrp": sq.rsrp,
                    "rsrq": sq.rsrq,
                    "sinr": sq.sinr,
                }
            )
            time.sleep(interval_sec)

        return measurements

    return _measure


@pytest.fixture
def wait_for_deregistration():
    """Helper fixture that waits for modem to lose network registration.

    Polls AT+CEREG? to check EPS (LTE) registration status until the modem
    reports it is no longer registered. This is more reliable than using a
    fixed sleep, as the time for a modem to detect loss of service varies
    depending on the modem's configuration and network conditions.
    """

    def _wait(modem, timeout_sec: float = DEREGISTRATION_TIMEOUT_SEC) -> bool:
        """
        Wait for modem to lose LTE network registration.

        Args:
            modem: ModemManager instance
            timeout_sec: Maximum time to wait for deregistration

        Returns:
            True if deregistered within timeout, False if still registered
        """
        start = time.time()

        while (time.time() - start) < timeout_sec:
            # Check EPS (LTE) registration status
            resp = modem.send_command("AT+CEREG?")
            match = re.search(r"\+CEREG:\s*\d+,(\d+)", resp)
            if match:
                stat = int(match.group(1))
                # 0 = not registered, not searching
                # 2 = not registered, searching
                # 3 = registration denied
                # 4 = unknown
                # (1 and 5 are registered states)
                if stat not in (1, 5):
                    return True
            time.sleep(DEREG_POLL_INTERVAL_SEC)

        return False

    return _wait
