"""
USB device power consumption measurement tests.

Tests measure USB VBUS current draw of the modem during various operating
conditions using a Saleae Logic MSO.

Requires the optional ``saleae-mso-api`` package.  When the package is not
installed the entire module is skipped at collection time — no SKIPPED
noise in normal test runs.

See README.power_consumption.md for hardware setup and methodology.
"""

import logging
import time

import pytest

# Skip entire module when saleae-mso-api is not installed.
pytest.importorskip(
    "saleae", reason="saleae-mso-api not installed — power consumption tests disabled"
)

from tests.constants import (
    AT_CMD_TIMEOUT,
    POWER_CONDITION_SETTLE_SEC,
    POWER_MODEM_TYPICAL_BUDGET_MA,
    POWER_SUBPROCESS_GRACE_SEC,
    POWER_SUPPLY_CONTINUOUS_MA,
    RADIO_OFF_SETTLE_SEC,
    RADIO_ON_SETTLE_SEC,
    TEST_TIMEOUT_POWER,
)
from tests.helpers import safe_cleanup

logger = logging.getLogger(__name__)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.slow
@pytest.mark.power_consumption
class TestPowerConsumption:
    """USB device power consumption measurement under various modem conditions.

    Each test starts the MSO capture **before** establishing the modem
    condition so the entire transition waveform is recorded.
    """

    # ------------------------------------------------------------------
    # 1. Disconnected — radio off (AT+CFUN=0)
    # ------------------------------------------------------------------
    @pytest.mark.timeout(TEST_TIMEOUT_POWER)
    def test_power_disconnected(
        self,
        modem,
        logic_mso,
        shunt_resistance,
        capture_duration,
        capture_power,
        power_mode,
        inamp_gain,
        tmp_path,
    ):
        """Measure power with radio off (AT+CFUN=0)."""
        # Start capture first — record the transition into radio-off
        cap = capture_power.start(
            logic_mso, shunt_resistance, capture_duration, tmp_path,
            mode=power_mode, gain=inamp_gain,
        )

        # Establish condition: turn radio off
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)

        # Wait for capture to complete naturally
        result = capture_power.wait(cap)

        # Restore radio
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_ON_SETTLE_SEC)

        logger.info(
            "DISCONNECTED: avg=%.1f mA, min=%.1f mA, max=%.1f mA",
            result["avg_current_ma"],
            result["min_current_ma"],
            result["max_current_ma"],
        )

        # Radio-off average must be well below the modem rail budget
        # (Component Selection Analysis: CELL_MOD_3V3_VCC = 350 mA typical)
        assert result["avg_current_ma"] < POWER_MODEM_TYPICAL_BUDGET_MA, (
            f"Radio-off avg current {result['avg_current_ma']:.1f} mA exceeds "
            f"modem rail budget {POWER_MODEM_TYPICAL_BUDGET_MA} mA"
        )

    # ------------------------------------------------------------------
    # 2. Connected idle — registered, no data transfer
    # ------------------------------------------------------------------
    @pytest.mark.timeout(TEST_TIMEOUT_POWER)
    def test_power_connected_idle(
        self,
        lte_cell,
        modem,
        logic_mso,
        shunt_resistance,
        capture_duration,
        capture_power,
        power_mode,
        inamp_gain,
        wait_for_registration,
        tmp_path,
    ):
        """Measure power when registered on LTE but idle (no data)."""
        cap = capture_power.start(
            logic_mso, shunt_resistance, capture_duration, tmp_path,
            mode=power_mode, gain=inamp_gain,
        )

        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        time.sleep(POWER_CONDITION_SETTLE_SEC)

        result = capture_power.wait(cap)

        logger.info(
            "CONNECTED IDLE: avg=%.1f mA, min=%.1f mA, max=%.1f mA",
            result["avg_current_ma"],
            result["min_current_ma"],
            result["max_current_ma"],
        )

        # Idle average should stay within the modem rail budget
        assert result["avg_current_ma"] < POWER_MODEM_TYPICAL_BUDGET_MA, (
            f"Idle avg current {result['avg_current_ma']:.1f} mA exceeds "
            f"modem rail budget {POWER_MODEM_TYPICAL_BUDGET_MA} mA"
        )

    # ------------------------------------------------------------------
    # 3. Transmit 1 KB
    # ------------------------------------------------------------------
    @pytest.mark.timeout(TEST_TIMEOUT_POWER)
    def test_power_transmit_1k(
        self,
        lte_cell,
        modem,
        logic_mso,
        shunt_resistance,
        capture_duration,
        capture_power,
        power_mode,
        inamp_gain,
        wait_for_registration,
        activate_data_connection_with_modem,
        generate_traffic,
        dau_with_internet,
        tmp_path,
    ):
        """Measure power during 1 KB data transmission."""
        cap = capture_power.start(
            logic_mso, shunt_resistance, capture_duration, tmp_path,
            mode=power_mode, gain=inamp_gain,
        )

        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to activate data connection")

        target_ip = dau_with_internet.get_lan_dau_info().ip_address
        generate_traffic.send_fixed(
            target_ip, 1024, timeout_sec=capture_duration + POWER_SUBPROCESS_GRACE_SEC
        )

        result = capture_power.wait(cap)

        logger.info(
            "TRANSMIT 1K: avg=%.1f mA, min=%.1f mA, max=%.1f mA",
            result["avg_current_ma"],
            result["min_current_ma"],
            result["max_current_ma"],
        )

        # TX average must stay within modem rail budget; peak within PSU limit
        assert result["avg_current_ma"] < POWER_MODEM_TYPICAL_BUDGET_MA, (
            f"TX-1K avg current {result['avg_current_ma']:.1f} mA exceeds "
            f"modem rail budget {POWER_MODEM_TYPICAL_BUDGET_MA} mA"
        )
        assert result["max_current_ma"] < POWER_SUPPLY_CONTINUOUS_MA, (
            f"TX-1K peak current {result['max_current_ma']:.1f} mA exceeds "
            f"PSU continuous limit {POWER_SUPPLY_CONTINUOUS_MA} mA"
        )

    # ------------------------------------------------------------------
    # 4. Transmit 4 KB
    # ------------------------------------------------------------------
    @pytest.mark.timeout(TEST_TIMEOUT_POWER)
    def test_power_transmit_4k(
        self,
        lte_cell,
        modem,
        logic_mso,
        shunt_resistance,
        capture_duration,
        capture_power,
        power_mode,
        inamp_gain,
        wait_for_registration,
        activate_data_connection_with_modem,
        generate_traffic,
        dau_with_internet,
        tmp_path,
    ):
        """Measure power during 4 KB data transmission."""
        cap = capture_power.start(
            logic_mso, shunt_resistance, capture_duration, tmp_path,
            mode=power_mode, gain=inamp_gain,
        )

        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to activate data connection")

        target_ip = dau_with_internet.get_lan_dau_info().ip_address
        generate_traffic.send_fixed(
            target_ip, 4096, timeout_sec=capture_duration + POWER_SUBPROCESS_GRACE_SEC
        )

        result = capture_power.wait(cap)

        logger.info(
            "TRANSMIT 4K: avg=%.1f mA, min=%.1f mA, max=%.1f mA",
            result["avg_current_ma"],
            result["min_current_ma"],
            result["max_current_ma"],
        )

        assert result["avg_current_ma"] < POWER_MODEM_TYPICAL_BUDGET_MA, (
            f"TX-4K avg current {result['avg_current_ma']:.1f} mA exceeds "
            f"modem rail budget {POWER_MODEM_TYPICAL_BUDGET_MA} mA"
        )
        assert result["max_current_ma"] < POWER_SUPPLY_CONTINUOUS_MA, (
            f"TX-4K peak current {result['max_current_ma']:.1f} mA exceeds "
            f"PSU continuous limit {POWER_SUPPLY_CONTINUOUS_MA} mA"
        )

    # ------------------------------------------------------------------
    # 5. Transmit continuous
    # ------------------------------------------------------------------
    @pytest.mark.timeout(TEST_TIMEOUT_POWER)
    def test_power_transmit_continuous(
        self,
        lte_cell,
        modem,
        logic_mso,
        shunt_resistance,
        capture_duration,
        capture_power,
        power_mode,
        inamp_gain,
        wait_for_registration,
        activate_data_connection_with_modem,
        generate_traffic,
        dau_with_internet,
        tmp_path,
    ):
        """Measure power during continuous data transmission."""
        cap = capture_power.start(
            logic_mso, shunt_resistance, capture_duration, tmp_path,
            mode=power_mode, gain=inamp_gain,
        )

        if not wait_for_registration(modem):
            pytest.skip("Modem did not register on cell")

        if not activate_data_connection_with_modem(modem, lte_cell):
            pytest.skip("Failed to activate data connection")

        target_ip = dau_with_internet.get_lan_dau_info().ip_address
        proc = generate_traffic.send_continuous(target_ip, capture_duration)
        if proc is None:
            pytest.skip("Could not find modem network interface for traffic")

        # Wait for capture to complete
        result = capture_power.wait(cap)

        # Let ping subprocess finish naturally
        try:
            proc.wait(timeout=capture_duration + POWER_SUBPROCESS_GRACE_SEC)
        except Exception:
            safe_cleanup(proc.terminate)

        logger.info(
            "TRANSMIT CONTINUOUS: avg=%.1f mA, min=%.1f mA, max=%.1f mA",
            result["avg_current_ma"],
            result["min_current_ma"],
            result["max_current_ma"],
        )

        assert result["avg_current_ma"] < POWER_MODEM_TYPICAL_BUDGET_MA, (
            f"Continuous TX avg current {result['avg_current_ma']:.1f} mA exceeds "
            f"modem rail budget {POWER_MODEM_TYPICAL_BUDGET_MA} mA"
        )
        assert result["max_current_ma"] < POWER_SUPPLY_CONTINUOUS_MA, (
            f"Continuous TX peak current {result['max_current_ma']:.1f} mA exceeds "
            f"PSU continuous limit {POWER_SUPPLY_CONTINUOUS_MA} mA"
        )
