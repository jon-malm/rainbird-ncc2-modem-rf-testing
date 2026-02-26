"""Shared data types for the modem interface."""

from dataclasses import dataclass


@dataclass
class SignalQuality:
    """Current signal quality measurements.

    Concrete modem implementations must return instances of this class
    from their get_signal_quality() method.
    """

    mode: str = "NOSERVICE"
    rssi: int | None = None  # Received Signal Strength Indicator (dBm)
    rsrp: int | None = None  # LTE Reference Signal Received Power (dBm)
    rsrq: int | None = None  # LTE Reference Signal Received Quality (dB)
    sinr: int | None = None  # LTE Signal to Interference+Noise Ratio (dB)
    rscp: int | None = None  # WCDMA Received Signal Code Power (dBm)
    ecio: int | None = None  # WCDMA Ec/Io (dB)

    def __str__(self) -> str:
        if self.mode == "LTE":
            return f"LTE: RSRP={self.rsrp}dBm RSRQ={self.rsrq}dB SINR={self.sinr}dB"
        elif self.mode == "WCDMA":
            return f"WCDMA: RSCP={self.rscp}dBm Ec/Io={self.ecio}dB"
        elif self.mode in ("GSM", "GPRS", "EDGE"):
            return f"{self.mode}: RSSI={self.rssi}dBm"
        return f"{self.mode}: No signal data"
