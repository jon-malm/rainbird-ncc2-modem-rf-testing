"""CMW500 controller and LTE signaling fixtures."""

import logging
import time
from typing import Generator

import pytest
from equipment_cmw500 import (
    CMW500Controller,
    LTEBearerConfig,
    LTECellConfig,
    LTESignaling,
)
from equipment_cmw500.models.enums import LTEBand, LTEBandwidth

from tests.constants import CELL_STABILIZE_SEC
from tests.helpers import safe_cleanup

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def cmw500_controller(cmw500_config) -> Generator[CMW500Controller, None, None]:
    """
    Session-scoped CMW500 controller.

    Connects once at the start of the test session and disconnects at the end.
    """
    controller = CMW500Controller(cmw500_config)
    controller.connect()

    yield controller

    # Cleanup: ensure cells are off
    controller.deactivate_all_cells()
    controller.disconnect()


@pytest.fixture(scope="function")
def cmw500(cmw500_controller) -> Generator[CMW500Controller, None, None]:
    """
    Function-scoped CMW500 fixture that prepares state between tests.

    Note: We use deactivate_all_cells() instead of reset_all() to avoid
    sending *RST which can disrupt the VISA connection on some instruments.

    If the connection was lost (e.g., due to VISA timeout in previous test),
    this fixture will attempt to reconnect and clear errors.
    """
    # Ensure connection is ready (reconnect if needed, clear errors)
    if not cmw500_controller.ensure_connection_ready():
        pytest.skip("Failed to establish CMW500 connection")

    # Deactivate any active cells before each test
    try:
        cmw500_controller.deactivate_all_cells()
    except Exception:
        # Connection may have issues, try to recover
        if not cmw500_controller.ensure_connection_ready():
            pytest.skip("CMW500 connection unstable")

    yield cmw500_controller

    # Cleanup after test - clear errors and deactivate cells
    try:
        cmw500_controller.clear_errors()
        cmw500_controller.deactivate_all_cells()
    except Exception:
        # Best effort cleanup - don't fail the test
        pass


def _force_cell_off(cmw500: CMW500Controller, cell_id: int = 1) -> None:
    """Force LTE cell OFF via direct SCPI, ignoring cached state.

    The -220 "access permission" error occurs when configure_cell() is
    called while the signaling application is still active or transitioning.
    This helper sends the OFF command directly and waits for completion,
    regardless of what the Python object thinks the state is.
    """
    sign = f"SIGN{cell_id}"
    try:
        state = cmw500.instrument.query(f"SOURce:LTE:{sign}:CELL:STATe?")
        if state.strip() not in ("OFF", "0"):
            logger.info("Cell %d state is %s, forcing OFF", cell_id, state.strip())
            cmw500.instrument.write(f"SOURce:LTE:{sign}:CELL:STATe OFF")
            cmw500.instrument.query_opc(timeout=15000)
    except Exception as e:
        logger.debug("Force cell OFF for cell %d: %s", cell_id, e)


@pytest.fixture(scope="function")
def lte_cell(cmw500) -> Generator[LTESignaling, None, None]:
    """
    Configured LTE cell fixture.

    Provides an LTE cell with default configuration, activated and ready
    for UE attachment.
    """
    # Ensure clean state: force cell OFF via SCPI and clear errors.
    # This prevents -220 "access permission" errors that occur when
    # configure_cell() is called while the cell is still active.
    _force_cell_off(cmw500, cell_id=1)
    cmw500.clear_errors()

    lte = cmw500.get_lte_signaling(cell_id=1)

    config = LTECellConfig(
        band=LTEBand.BAND_7,
        bandwidth=LTEBandwidth.BW_10_MHZ,
        dl_earfcn=3100,
        dl_power_dbm=-60.0,
    )

    bearer = LTEBearerConfig(apn="test", pdn_type="IPV4", qci=9)

    try:
        lte.configure_cell(config)
        lte.activate_cell()
        # Configure bearer after cell is active — APN is a DAU setting
        # that may not be available on all CMW500 configurations
        lte.configure_default_bearer(bearer)
    except Exception as e:
        # Try to recover and retry once
        if cmw500.ensure_connection_ready():
            _force_cell_off(cmw500, cell_id=1)
            cmw500.clear_errors()
            lte = cmw500.get_lte_signaling(cell_id=1)
            try:
                lte.configure_cell(config)
                lte.activate_cell()
                lte.configure_default_bearer(bearer)
            except Exception as e2:
                pytest.skip(
                    f"Failed to configure/activate LTE cell after recovery: {e2}"
                )
        else:
            pytest.skip(f"Failed to configure/activate LTE cell: {e}")

    # Allow cell to stabilize before tests run
    time.sleep(CELL_STABILIZE_SEC)

    yield lte

    safe_cleanup(lte.deactivate_cell)


@pytest.fixture(scope="function")
def carrier_cells(cmw500) -> Generator[dict, None, None]:
    """Two intra-frequency LTE cells for carrier-level fallback testing.

    Simulates multiple cells at the same RAT so the modem can reselect
    between them without requiring an eSIM profile switch.  SIB3/SIB4
    neighbor cell info is configured so the modem knows about both cells.

    Provides:
        dict with keys "primary" and "fallback", each an LTESignaling handle.
        - primary: PCI 0, -60 dBm (strong)
        - fallback: PCI 1, -60 dBm (equal)
        Both on Band 7, EARFCN 3100, same PLMN (001/01).
    """
    _force_cell_off(cmw500, cell_id=1)
    _force_cell_off(cmw500, cell_id=2)
    cmw500.clear_errors()

    band = LTEBand.BAND_7
    earfcn = 3100
    pci1, pci2 = 0, 1

    lte1 = cmw500.get_lte_signaling(cell_id=1)
    lte2 = cmw500.get_lte_signaling(cell_id=2)

    config_primary = LTECellConfig(
        band=band,
        bandwidth=LTEBandwidth.BW_10_MHZ,
        dl_earfcn=earfcn,
        physical_cell_id=pci1,
        dl_power_dbm=-60.0,
    )
    config_fallback = LTECellConfig(
        band=band,
        bandwidth=LTEBandwidth.BW_10_MHZ,
        dl_earfcn=earfcn,
        physical_cell_id=pci2,
        dl_power_dbm=-60.0,
    )

    bearer = LTEBearerConfig(apn="test", pdn_type="IPV4", qci=9)

    try:
        lte1.configure_cell(config_primary)
        lte1.configure_cell_reselection(s_intra_search_p=62)
        lte1.configure_neighbor_cell(1, band, earfcn, pci2)
        lte1.activate_cell()
        lte1.configure_default_bearer(bearer)

        lte2.configure_cell(config_fallback)
        lte2.configure_cell_reselection(s_intra_search_p=62)
        lte2.configure_neighbor_cell(1, band, earfcn, pci1)
        lte2.activate_cell()
        lte2.configure_default_bearer(bearer)
    except Exception as e:
        safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
        pytest.skip(f"Failed to configure dual-cell LTE: {e}")

    time.sleep(CELL_STABILIZE_SEC)

    yield {"primary": lte1, "fallback": lte2}

    safe_cleanup(lte1.deactivate_cell, lte2.deactivate_cell)
