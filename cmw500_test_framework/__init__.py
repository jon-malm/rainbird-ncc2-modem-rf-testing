"""
CMW500 Test Framework

A Python test framework for network simulation and RF testing
on the Rohde & Schwarz CMW500 Wideband Radio Communication Tester.

Supports:
- LTE/LTE-A signaling and measurements
- 5G NR (with CMX500 extension)
- WCDMA/GSM signaling
- General purpose RF testing
- Fading channel simulation
- Network emulation

Usage:
    from cmw500_test_framework import CMW500Client

    client = CMW500Client("192.168.1.100")
    client.connect()
    print(client.get_identification())
"""

__version__ = "0.1.0"
__author__ = "RF Testing Team"

from .core.client import CMW500Client
from .core.scpi import SCPIConnection
from .core.config import Config

__all__ = [
    "CMW500Client",
    "SCPIConnection",
    "Config",
]
