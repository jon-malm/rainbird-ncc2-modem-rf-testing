"""Saleae Logic MSO fixtures for power consumption testing.

Requires the optional ``saleae-mso-api`` package.  Install with::

    uv sync --group power
"""

import logging
import threading
from pathlib import Path

import pytest

from tests.constants import (
    POWER_ANALOG_CHANNEL,
    POWER_CAPTURE_DURATION_SEC,
    POWER_DEFAULT_INAMP_GAIN,
    POWER_DEFAULT_MODE,
    POWER_DEFAULT_SHUNT_OHMS,
    POWER_DIFFERENTIAL_CHANNEL_A,
    POWER_DIFFERENTIAL_CHANNEL_B,
    POWER_SAMPLE_RATE_HZ,
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def logic_mso(request):
    """Session-scoped Saleae Logic MSO controller.

    Skips all dependent tests if saleae-mso-api is not installed
    or if no Logic MSO device is detected.
    """
    try:
        from saleae import mso_api
    except ImportError:
        pytest.skip(
            "saleae-mso-api not installed. Install with: uv sync --group power"
        )

    serial_number = request.config.getoption("--logic-mso-serial", default=None)

    try:
        if serial_number:
            mso = mso_api.MSO(serial_number=serial_number)
        else:
            mso = mso_api.MSO()
    except Exception as e:
        pytest.skip(f"Saleae Logic MSO not available: {e}")

    yield mso


@pytest.fixture(scope="session")
def shunt_resistance(request) -> float:
    """Current shunt resistance from CLI option or default."""
    value = request.config.getoption("--shunt-resistance", default=None)
    return float(value) if value else POWER_DEFAULT_SHUNT_OHMS


@pytest.fixture(scope="session")
def capture_duration(request) -> float:
    """Power capture duration from CLI option or default."""
    value = request.config.getoption("--capture-duration", default=None)
    return float(value) if value else POWER_CAPTURE_DURATION_SEC


@pytest.fixture(scope="session")
def power_mode(request) -> str:
    """Measurement mode from CLI option or default."""
    value = request.config.getoption("--power-mode", default=None)
    return value if value else POWER_DEFAULT_MODE


@pytest.fixture(scope="session")
def inamp_gain(request) -> float:
    """Instrumentation amplifier gain from CLI option or default."""
    value = request.config.getoption("--inamp-gain", default=None)
    return float(value) if value else POWER_DEFAULT_INAMP_GAIN


@pytest.fixture
def capture_power():
    """Helper fixture that captures power data from the Saleae Logic MSO.

    Supports two measurement topologies (selected via ``--power-mode``):

    ``differential``
        Two Saleae channels measure Node A and Node B of the high-side
        shunt.  Current is computed as ``(CH_A - CH_B) / R_shunt``.

    ``inamp``
        A single Saleae channel reads the output of an instrumentation
        amplifier across the shunt.  Current is computed as
        ``V_out / (gain * R_shunt)``.

    Usage::

        cap = capture_power.start(
            logic_mso, shunt_resistance, capture_duration, tmp_path,
            mode=power_mode, gain=inamp_gain,
        )
        # ... establish modem condition here ...
        result = capture_power.wait(cap)
    """
    import numpy as np
    from saleae import mso_api

    def _start(
        logic_mso_instance,
        shunt_ohms: float,
        duration_sec: float,
        save_dir: Path,
        *,
        mode: str = POWER_DEFAULT_MODE,
        gain: float = POWER_DEFAULT_INAMP_GAIN,
        sample_rate: float = POWER_SAMPLE_RATE_HZ,
    ) -> dict:
        """Start an MSO timed capture in a background thread.

        Returns a handle dict to pass to ``_wait()``.
        """
        if mode == "differential":
            enabled_channels = [
                mso_api.AnalogChannel(
                    channel=POWER_DIFFERENTIAL_CHANNEL_A, name="node_a",
                ),
                mso_api.AnalogChannel(
                    channel=POWER_DIFFERENTIAL_CHANNEL_B, name="node_b",
                ),
            ]
            ch_desc = (
                f"CH{POWER_DIFFERENTIAL_CHANNEL_A} - "
                f"CH{POWER_DIFFERENTIAL_CHANNEL_B}"
            )
        else:
            enabled_channels = [
                mso_api.AnalogChannel(
                    channel=POWER_ANALOG_CHANNEL, name="vbus_shunt",
                ),
            ]
            ch_desc = f"CH{POWER_ANALOG_CHANNEL} (in-amp gain={gain})"

        capture_config = mso_api.CaptureConfig(
            enabled_channels=enabled_channels,
            analog_settings=mso_api.AnalogSettings(sample_rate=sample_rate),
            capture_settings=mso_api.TimedCapture(
                capture_length_seconds=duration_sec,
            ),
        )

        handle = {
            "capture": None,
            "error": None,
            "shunt_ohms": shunt_ohms,
            "duration_sec": duration_sec,
            "mode": mode,
            "gain": gain,
        }

        def _run_capture():
            try:
                handle["capture"] = logic_mso_instance.capture(
                    capture_config,
                    save_dir=save_dir,
                    timeout_secs=duration_sec + 30.0,
                )
            except Exception as e:
                handle["error"] = e

        thread = threading.Thread(target=_run_capture, daemon=True)
        thread.start()
        handle["thread"] = thread

        logger.info(
            "MSO capture started: %.1fs @ %s Hz, mode=%s (%s)",
            duration_sec,
            f"{sample_rate:,.0f}",
            mode,
            ch_desc,
        )
        return handle

    def _wait(handle: dict) -> dict:
        """Block until the capture completes and return computed results."""
        thread = handle["thread"]
        # Allow generous timeout: capture duration + 60s for device overhead
        thread.join(timeout=handle["duration_sec"] + 60.0)

        if thread.is_alive():
            raise TimeoutError("MSO capture did not complete in time")

        if handle["error"] is not None:
            raise handle["error"]

        capture = handle["capture"]
        shunt_ohms = handle["shunt_ohms"]
        mode = handle["mode"]

        if mode == "differential":
            voltages_a = capture.analog_data["node_a"].voltages
            voltages_b = capture.analog_data["node_b"].voltages
            v_shunt = voltages_a - voltages_b
            currents_a = v_shunt / shunt_ohms
            avg_voltage_mv = float(np.mean(v_shunt) * 1000.0)
            num_samples = len(voltages_a)
        else:
            v_out = capture.analog_data["vbus_shunt"].voltages
            gain = handle["gain"]
            currents_a = v_out / (gain * shunt_ohms)
            avg_voltage_mv = float(np.mean(v_out) * 1000.0)
            num_samples = len(v_out)

        currents_ma = currents_a * 1000.0

        result = {
            "avg_current_ma": float(np.mean(currents_ma)),
            "min_current_ma": float(np.min(currents_ma)),
            "max_current_ma": float(np.max(currents_ma)),
            "std_current_ma": float(np.std(currents_ma)),
            "num_samples": num_samples,
            "duration_sec": handle["duration_sec"],
            "shunt_ohms": shunt_ohms,
            "avg_voltage_mv": avg_voltage_mv,
        }

        logger.info(
            "MSO capture complete (%s): avg=%.1f mA, min=%.1f mA, max=%.1f mA "
            "(%d samples over %.1fs)",
            mode,
            result["avg_current_ma"],
            result["min_current_ma"],
            result["max_current_ma"],
            result["num_samples"],
            result["duration_sec"],
        )
        return result

    helpers = {"start": staticmethod(_start), "wait": staticmethod(_wait)}
    return type("CaptureHelper", (), helpers)()
