"""Modem interface abstraction layer.

Provides an abstract base class for modem control so that the test
framework is decoupled from any specific modem hardware.

Public API::

    ModemManager        ABC defining the modem control interface
    SignalQuality       Shared data class for signal measurements
    EG21GModemManager   Concrete adapter for the Quectel EG21-G
    H7ModemManager      Concrete adapter for STM32H7 board (via eRPC)
"""

from ._abc import ModemManager
from ._types import SignalQuality
from .eg21g import EG21GModemManager
from .h7 import H7ModemManager

__all__ = ["ModemManager", "SignalQuality", "EG21GModemManager", "H7ModemManager"]
