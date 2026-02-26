"""Concrete adapter for the Quectel EG21-G modem (modem-manager-eg21 submodule)."""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import serial as _serial

from ._abc import ModemManager
from ._types import SignalQuality

# Add the submodule to sys.path so we can import from it.
_submodule_path = str(Path(__file__).resolve().parents[1] / "modem-manager-eg21")
if _submodule_path not in sys.path:
    sys.path.insert(0, _submodule_path)

from modem_manager import ModemManager as _EG21ModemManager  # noqa: E402
from modem_manager import SignalQuality as _EG21SignalQuality  # noqa: E402


class EG21GModemManager(ModemManager):
    """Adapter wrapping the modem-manager-eg21 concrete implementation.

    Delegates all operations to the underlying EG21-G ``ModemManager``
    instance and converts submodule-specific types to framework types.
    """

    def __init__(
        self,
        port: str = None,
        baudrate: int = 115200,
        timeout: float = 1.0,
    ):
        self._inner = _EG21ModemManager(
            port=port, baudrate=baudrate, timeout=timeout
        )

    # --- Connection lifecycle ---

    def find_at_port(self) -> Optional[str]:
        return self._inner.find_at_port()

    def connect(self, port: str = None) -> bool:
        return self._inner.connect(port)

    def disconnect(self) -> None:
        self._inner.disconnect()

    def is_connected(self) -> bool:
        return self._inner.is_connected()

    # --- AT command interface ---

    def send_command(
        self,
        cmd: str,
        timeout: float = None,
        interrupt_check: Callable[[], bool] = None,
    ) -> str:
        return self._inner.send_command(
            cmd, timeout=timeout, interrupt_check=interrupt_check
        )

    # --- Modem information ---

    def get_modem_info(self) -> dict:
        return self._inner.get_modem_info()

    def get_sim_status(self) -> str:
        return self._inner.get_sim_status()

    # --- Network status ---

    def get_signal_quality(self) -> SignalQuality:
        sq: _EG21SignalQuality = self._inner.get_signal_quality()
        return SignalQuality(
            mode=sq.mode,
            rssi=sq.rssi,
            rsrp=sq.rsrp,
            rsrq=sq.rsrq,
            sinr=sq.sinr,
            rscp=sq.rscp,
            ecio=sq.ecio,
        )

    def is_registered(self) -> bool:
        return self._inner.is_registered()

    # --- eSIM profile management ---

    def list_esim_profiles(self) -> list[dict] | None:
        profiles = self._inner.list_esim_profiles()
        if profiles is None:
            return None
        return [
            {
                "iccid": p.iccid,
                "status": p.status,
                "nickname": p.nickname,
                "provider": p.provider,
            }
            for p in profiles
        ]

    def switch_esim_profile(self, iccid: str) -> bool:
        return self._inner.enable_esim_profile(iccid)

    def get_active_iccid(self) -> str | None:
        return self._inner.get_active_esim_iccid()

    # --- Serial interface ---

    @property
    def port(self) -> Optional[str]:
        return self._inner.port

    @property
    def serial(self) -> Optional[_serial.Serial]:
        return self._inner.serial
