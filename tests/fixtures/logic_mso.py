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
    POWER_DEFAULT_SHUNT_OHMS,
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


@pytest.fixture
def capture_power():
    """Helper fixture that captures power data from the Saleae Logic MSO.

    Returns a callable with ``start()`` and ``wait()`` methods so the caller
    can establish modem conditions *while* the capture is running::

        cap = capture_power.start(logic_mso, shunt_resistance, duration, save_dir)
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
        channel: int = POWER_ANALOG_CHANNEL,
        sample_rate: float = POWER_SAMPLE_RATE_HZ,
        channel_name: str = "vbus_shunt",
    ) -> dict:
        """Start an MSO timed capture in a background thread.

        Returns a handle dict to pass to ``_wait()``.
        """
        capture_config = mso_api.CaptureConfig(
            enabled_channels=[
                mso_api.AnalogChannel(channel=channel, name=channel_name),
            ],
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
            "channel_name": channel_name,
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
            "MSO capture started: %.1fs @ %s Hz on channel %d",
            duration_sec,
            f"{sample_rate:,.0f}",
            channel,
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
        channel_name = handle["channel_name"]
        shunt_ohms = handle["shunt_ohms"]

        voltages = capture.analog_data[channel_name].voltages
        currents_a = voltages / shunt_ohms
        currents_ma = currents_a * 1000.0

        result = {
            "avg_current_ma": float(np.mean(currents_ma)),
            "min_current_ma": float(np.min(currents_ma)),
            "max_current_ma": float(np.max(currents_ma)),
            "std_current_ma": float(np.std(currents_ma)),
            "num_samples": len(voltages),
            "duration_sec": handle["duration_sec"],
            "shunt_ohms": shunt_ohms,
            "avg_voltage_mv": float(np.mean(voltages) * 1000.0),
        }

        logger.info(
            "MSO capture complete: avg=%.1f mA, min=%.1f mA, max=%.1f mA "
            "(%d samples over %.1fs)",
            result["avg_current_ma"],
            result["min_current_ma"],
            result["max_current_ma"],
            result["num_samples"],
            result["duration_sec"],
        )
        return result

    helpers = {"start": staticmethod(_start), "wait": staticmethod(_wait)}
    return type("CaptureHelper", (), helpers)()
