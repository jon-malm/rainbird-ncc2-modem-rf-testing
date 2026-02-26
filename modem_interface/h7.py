"""H7ModemManager — controls a Quectel modem via the STM32H7 board over eRPC.

The STM32H7 board manages the modem over USB.  This adapter delegates all
operations to eRPC services running on the H7 (TCP, port 5674).

Requires the ``erpc`` package: install with ``uv sync --group h7``.
"""

import logging
from collections.abc import Callable
from typing import Optional

from ._types import SignalQuality as FrameworkSignalQuality

logger = logging.getLogger(__name__)

_SENTINEL = -128  # eRPC int16 sentinel for "not available"

DEFAULT_HOST = "192.168.1.100"
DEFAULT_PORT = 5674


class H7ModemManager:
    """ModemManager implementation that talks to the STM32H7 via eRPC."""

    def __init__(self, host: str = DEFAULT_HOST, erpc_port: int = DEFAULT_PORT):
        self._host = host
        self._erpc_port = erpc_port
        self._transport = None
        self._client_manager = None
        self._modem_svc = None
        self._test_svc = None

    # --- Connection lifecycle ---

    def find_at_port(self) -> Optional[str]:
        return None

    def connect(self, port: str = None) -> bool:
        """Connect to the H7 eRPC server.

        Args:
            port: Optional ``host:port`` override (for CLI/fixture compat).
        """
        if port:
            host, _, port_str = port.rpartition(":")
            if host and port_str:
                self._host = host
                self._erpc_port = int(port_str)

        try:
            import erpc  # noqa: I001 — lazy import, order irrelevant
            from ._erpc_gen.modem_service.client import (
                ModemServiceClient,
                TestServiceClient,
            )

            self._transport = erpc.transport.TCPTransport(
                self._host, self._erpc_port, True
            )
            self._client_manager = erpc.client.ClientManager(
                self._transport, erpc.basic_codec.BasicCodec()
            )
            self._modem_svc = ModemServiceClient(self._client_manager)
            self._test_svc = TestServiceClient(self._client_manager)

            alive = self._modem_svc.is_modem_alive()
            if not alive:
                logger.warning("eRPC connected but modem not alive")
            return alive
        except Exception:
            logger.exception("Failed to connect to H7 eRPC server")
            self._cleanup()
            return False

    def disconnect(self) -> None:
        self._cleanup()

    def is_connected(self) -> bool:
        return self._transport is not None

    # --- AT command interface ---

    def send_command(
        self,
        cmd: str,
        timeout: float = None,
        interrupt_check: Callable[[], bool] = None,
    ) -> str:
        if not self._test_svc:
            return ""
        timeout_ms = int((timeout or 5) * 1000)
        try:
            resp = self._test_svc.send_at_command(cmd, timeout_ms)
            return resp.response or ""
        except Exception:
            logger.exception("send_command failed: %s", cmd)
            return ""

    # --- Modem information ---

    def get_modem_info(self) -> dict:
        if not self._modem_svc:
            return {}
        try:
            info = self._modem_svc.get_modem_info()
            return {
                "manufacturer": info.manufacturer or "",
                "model": info.model or "",
                "firmware": info.firmware or "",
                "imei": info.imei or "",
            }
        except Exception:
            logger.exception("get_modem_info failed")
            return {}

    def get_sim_status(self) -> str:
        if not self._modem_svc:
            return ""
        try:
            return self._modem_svc.get_sim_status() or ""
        except Exception:
            logger.exception("get_sim_status failed")
            return ""

    # --- Network status ---

    def get_signal_quality(self) -> FrameworkSignalQuality:
        if not self._modem_svc:
            return FrameworkSignalQuality()
        try:
            sq = self._modem_svc.get_signal_quality()
            return FrameworkSignalQuality(
                mode=sq.mode or "NOSERVICE",
                rssi=_nullable(sq.rssi),
                rsrp=_nullable(sq.rsrp),
                rsrq=_nullable(sq.rsrq),
                sinr=_nullable(sq.sinr),
                rscp=_nullable(sq.rscp),
                ecio=_nullable(sq.ecio),
            )
        except Exception:
            logger.exception("get_signal_quality failed")
            return FrameworkSignalQuality()

    def is_registered(self) -> bool:
        if not self._modem_svc:
            return False
        try:
            return self._modem_svc.is_registered()
        except Exception:
            logger.exception("is_registered failed")
            return False

    # --- eSIM profile management ---

    def list_esim_profiles(self) -> list[dict] | None:
        if not self._modem_svc:
            return None
        try:
            result = self._modem_svc.list_esim_profiles()
            return [
                {
                    "iccid": p.iccid or "",
                    "status": p.status or "",
                    "nickname": p.nickname or "",
                    "provider": p.provider or "",
                }
                for p in (result.profiles or [])
            ]
        except Exception:
            logger.exception("list_esim_profiles failed")
            return None

    def switch_esim_profile(self, iccid: str) -> bool:
        if not self._modem_svc:
            return False
        try:
            return self._modem_svc.switch_esim_profile(iccid)
        except Exception:
            logger.exception("switch_esim_profile failed")
            return False

    def get_active_iccid(self) -> str | None:
        if not self._modem_svc:
            return None
        try:
            result = self._modem_svc.get_active_iccid()
            return result if result else None
        except Exception:
            logger.exception("get_active_iccid failed")
            return None

    # --- Serial interface (not applicable for H7) ---

    @property
    def port(self) -> Optional[str]:
        return f"{self._host}:{self._erpc_port}"

    @property
    def serial(self):
        return None

    # --- Internal helpers ---

    def _cleanup(self) -> None:
        self._modem_svc = None
        self._test_svc = None
        self._client_manager = None
        if self._transport:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None


def _nullable(value: int) -> int | None:
    """Convert eRPC int16 sentinel -128 to None."""
    return None if value == _SENTINEL else value
