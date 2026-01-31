"""DAU (Data Application Unit) fixtures."""

import logging
import time
from typing import Generator

import pytest
from equipment_cmw500.dau.dau_controller import DAUController

logger = logging.getLogger(__name__)

# Switching the LAN DAU interface mode (e.g. standalone → DHCP) can
# briefly disrupt the CMW500 network stack, dropping the VISA session.
# Allow time for DHCP negotiation and then reconnect.
_DAU_RECONFIG_SETTLE_SEC = 5.0


@pytest.fixture(scope="function")
def dau_with_internet(cmw500) -> Generator[DAUController, None, None]:
    """
    DAU configured for external internet routing.

    Sets up the Data Application Unit with DHCP on LAN DAU interface
    and NAT enabled for UE traffic.

    Switching from standalone to DHCP may temporarily drop the VISA
    connection.  If that happens we wait for the CMW500 network stack
    to settle and reconnect before continuing.
    """
    dau = cmw500.get_dau_controller()
    try:
        dau.configure_for_external_routing()
    except Exception as e:
        # Switching the LAN DAU mode (especially to DHCP) reconfigures the
        # CMW500 network stack, which drops the VISA/HiSLIP session.
        # Wait for DHCP to complete and then reconnect.
        logger.warning(
            "DAU configuration disrupted VISA connection (%s), reconnecting", e
        )
        time.sleep(_DAU_RECONFIG_SETTLE_SEC)
        if not cmw500.ensure_connection_ready():
            pytest.skip("CMW500 connection lost after DAU reconfiguration")
        # reconnect() clears cached controllers; get a fresh one.
        # The LAN mode change already took effect — only NAT/DNS may
        # still need configuring, but configure_for_external_routing()
        # is safe to re-run (DHCP write is idempotent).
        dau = cmw500.get_dau_controller()
        try:
            dau.configure_for_external_routing()
        except Exception as e2:
            # If it fails again, the DHCP command itself may be
            # re-triggering the disruption. Wait longer and retry once.
            logger.warning("Second DAU config attempt failed (%s), final retry", e2)
            time.sleep(_DAU_RECONFIG_SETTLE_SEC * 2)
            if not cmw500.ensure_connection_ready():
                pytest.skip("CMW500 connection lost after DAU reconfiguration")
            dau = cmw500.get_dau_controller()
            dau.configure_for_external_routing()

    yield dau


@pytest.fixture(scope="function")
def end_to_end_data_path(lte_cell, dau_with_internet) -> Generator[dict, None, None]:
    """
    Full end-to-end data path fixture.

    Provides:
    - Activated LTE cell
    - DAU configured for external routing
    - Ready for modem attachment and internet connectivity testing

    Data path: Modem -> CMW500 LTE Cell -> DAU -> LAN DAU -> Internet
    """
    yield {
        "cell": lte_cell,
        "dau": dau_with_internet,
    }
