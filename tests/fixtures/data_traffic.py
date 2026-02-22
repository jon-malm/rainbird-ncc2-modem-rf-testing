"""Data traffic generation fixtures for power consumption testing."""

import logging
import os
import subprocess

import pytest

from tests.constants import POWER_SUBPROCESS_GRACE_SEC

logger = logging.getLogger(__name__)


@pytest.fixture
def generate_traffic():
    """Helper fixture that generates data traffic through the modem interface.

    Returns a namespace with:

    - ``send_fixed(target_ip, total_bytes, interface=None)`` — send a
      specific amount of data via ICMP ping.  Blocks until complete.
    - ``send_continuous(target_ip, duration_sec, interface=None)`` — start
      continuous ping traffic in a background subprocess.  Returns a
      ``Popen`` object; caller should use
      ``proc.wait(timeout=duration + POWER_SUBPROCESS_GRACE_SEC)``.
    - ``find_interface()`` — auto-detect the modem USB ECM interface.
    """

    def _find_interface() -> str | None:
        """Find the modem's USB ECM network interface."""
        result = subprocess.run(
            ["ip", "-br", "link"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if not parts:
                continue
            iface = parts[0]
            if any(p in iface.lower() for p in ("usb", "wwan")):
                usb_path = f"/sys/class/net/{iface}/device"
                if os.path.exists(usb_path):
                    real_path = os.path.realpath(usb_path)
                    if "usb" in real_path.lower():
                        return iface
        return None

    def _send_fixed(
        target_ip: str,
        total_bytes: int,
        interface: str | None = None,
        timeout_sec: float | None = None,
    ) -> bool:
        """Send a specific amount of data using ICMP ping.

        Args:
            target_ip: IP address to ping (e.g. DAU gateway).
            total_bytes: Approximate total payload bytes to transmit.
            interface: Network interface name (auto-detect if None).
            timeout_sec: Subprocess timeout.  Defaults to
                ``capture_duration + POWER_SUBPROCESS_GRACE_SEC``.

        Returns:
            True if traffic was sent successfully.
        """
        iface = interface or _find_interface()
        if not iface:
            logger.warning("Could not find modem network interface")
            return False

        packet_size = min(total_bytes, 1024)
        count = max(1, total_bytes // packet_size)

        cmd = [
            "ping",
            "-I", iface,
            "-c", str(count),
            "-s", str(packet_size),
            "-i", "0.2",
            "-W", "5",
            target_ip,
        ]

        if timeout_sec is None:
            timeout_sec = count * 6 + POWER_SUBPROCESS_GRACE_SEC

        logger.info(
            "Sending %d bytes via ping (%d x %d) on %s -> %s",
            total_bytes, count, packet_size, iface, target_ip,
        )

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_sec
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.warning("Ping traffic timed out after %.1fs", timeout_sec)
            return False
        except Exception as e:
            logger.warning("Ping traffic generation failed: %s", e)
            return False

    def _send_continuous(
        target_ip: str,
        duration_sec: float,
        interface: str | None = None,
    ) -> subprocess.Popen:
        """Start continuous ping traffic in a background subprocess.

        The caller should wait for the process to finish naturally::

            proc = send_continuous(ip, duration)
            # ... MSO capture runs ...
            proc.wait(timeout=duration + POWER_SUBPROCESS_GRACE_SEC)

        Args:
            target_ip: IP address to target.
            duration_sec: Approximate duration of traffic.
            interface: Network interface name (auto-detect if None).

        Returns:
            Popen object for the background ping process.
        """
        iface = interface or _find_interface()
        if not iface:
            logger.warning("Could not find modem network interface")
            return None

        # ~10 packets per second for the requested duration
        count = int(duration_sec * 10)

        cmd = [
            "ping",
            "-I", iface,
            "-c", str(count),
            "-s", "1024",
            "-i", "0.1",
            "-W", "5",
            target_ip,
        ]

        logger.info(
            "Starting continuous ping: %d packets on %s -> %s",
            count, iface, target_ip,
        )

        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

    return type(
        "TrafficHelper",
        (),
        {
            "send_fixed": staticmethod(_send_fixed),
            "send_continuous": staticmethod(_send_continuous),
            "find_interface": staticmethod(_find_interface),
        },
    )()
