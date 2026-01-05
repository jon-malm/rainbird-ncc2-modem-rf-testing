"""
Helper Utilities

Common utility functions for the test framework.
"""

import re
from typing import Union


def format_frequency(freq_hz: float, precision: int = 3) -> str:
    """
    Format frequency in human-readable form.

    Args:
        freq_hz: Frequency in Hz
        precision: Decimal precision

    Returns:
        Formatted string (e.g., "1.95 GHz")
    """
    if freq_hz >= 1e9:
        return f"{freq_hz / 1e9:.{precision}f} GHz"
    elif freq_hz >= 1e6:
        return f"{freq_hz / 1e6:.{precision}f} MHz"
    elif freq_hz >= 1e3:
        return f"{freq_hz / 1e3:.{precision}f} kHz"
    else:
        return f"{freq_hz:.{precision}f} Hz"


def format_power(power_dbm: float, precision: int = 1) -> str:
    """
    Format power level.

    Args:
        power_dbm: Power in dBm
        precision: Decimal precision

    Returns:
        Formatted string (e.g., "-85.0 dBm")
    """
    return f"{power_dbm:.{precision}f} dBm"


def parse_frequency(freq_str: str) -> float:
    """
    Parse frequency string to Hz.

    Args:
        freq_str: Frequency string (e.g., "1.95 GHz", "1950 MHz", "1950000000")

    Returns:
        Frequency in Hz
    """
    freq_str = freq_str.strip().upper()

    # Try to extract number and unit
    match = re.match(r"([\d.]+)\s*(GHZ|MHZ|KHZ|HZ)?", freq_str)
    if not match:
        raise ValueError(f"Invalid frequency format: {freq_str}")

    value = float(match.group(1))
    unit = match.group(2) or "HZ"

    multipliers = {
        "GHZ": 1e9,
        "MHZ": 1e6,
        "KHZ": 1e3,
        "HZ": 1,
    }

    return value * multipliers[unit]


def parse_power(power_str: str) -> float:
    """
    Parse power string to dBm.

    Args:
        power_str: Power string (e.g., "-85 dBm", "-85.0", "-85 dbm")

    Returns:
        Power in dBm
    """
    power_str = power_str.strip().upper()

    # Remove unit suffix
    power_str = re.sub(r"\s*DBM?\s*$", "", power_str)

    return float(power_str)


def calculate_path_loss(
    frequency_mhz: float,
    distance_km: float,
    model: str = "FREE_SPACE",
) -> float:
    """
    Calculate path loss using various models.

    Args:
        frequency_mhz: Frequency in MHz
        distance_km: Distance in km
        model: Path loss model

    Returns:
        Path loss in dB
    """
    import math

    if model == "FREE_SPACE":
        # Free Space Path Loss
        # FSPL(dB) = 32.45 + 20*log10(f_MHz) + 20*log10(d_km)
        return 32.45 + 20 * math.log10(frequency_mhz) + 20 * math.log10(max(distance_km, 0.001))

    elif model == "COST231_HATA":
        # COST-231 Hata Model (urban macro)
        # Valid for 1500-2000 MHz
        # Lp = 46.3 + 33.9*log10(f) - 13.82*log10(hb) + (44.9 - 6.55*log10(hb))*log10(d) + Cm
        hb = 30  # Base station height (m)
        cm = 3   # Metropolitan center correction
        if distance_km < 0.001:
            distance_km = 0.001
        return (46.3 + 33.9 * math.log10(frequency_mhz) - 13.82 * math.log10(hb)
                + (44.9 - 6.55 * math.log10(hb)) * math.log10(distance_km) + cm)

    else:
        raise ValueError(f"Unknown path loss model: {model}")


def doppler_from_speed(speed_kmh: float, frequency_mhz: float) -> float:
    """
    Calculate Doppler frequency from speed.

    Args:
        speed_kmh: Speed in km/h
        frequency_mhz: Carrier frequency in MHz

    Returns:
        Doppler frequency in Hz
    """
    # fd = v * f / c
    # where v is velocity in m/s, f is frequency in Hz, c is speed of light
    c = 3e8  # Speed of light in m/s
    v = speed_kmh * 1000 / 3600  # Convert km/h to m/s
    f = frequency_mhz * 1e6  # Convert MHz to Hz
    return v * f / c


def speed_from_doppler(doppler_hz: float, frequency_mhz: float) -> float:
    """
    Calculate speed from Doppler frequency.

    Args:
        doppler_hz: Doppler frequency in Hz
        frequency_mhz: Carrier frequency in MHz

    Returns:
        Speed in km/h
    """
    c = 3e8  # Speed of light in m/s
    f = frequency_mhz * 1e6  # Convert MHz to Hz
    v = doppler_hz * c / f  # Velocity in m/s
    return v * 3600 / 1000  # Convert m/s to km/h


def lte_band_to_frequency(band: int, direction: str = "DL") -> tuple:
    """
    Get frequency range for LTE band.

    Args:
        band: LTE band number
        direction: "DL" or "UL"

    Returns:
        Tuple of (low_freq_mhz, high_freq_mhz)
    """
    # Common LTE FDD bands
    bands = {
        1: {"DL": (2110, 2170), "UL": (1920, 1980)},
        2: {"DL": (1930, 1990), "UL": (1850, 1910)},
        3: {"DL": (1805, 1880), "UL": (1710, 1785)},
        4: {"DL": (2110, 2155), "UL": (1710, 1755)},
        5: {"DL": (869, 894), "UL": (824, 849)},
        7: {"DL": (2620, 2690), "UL": (2500, 2570)},
        8: {"DL": (925, 960), "UL": (880, 915)},
        12: {"DL": (729, 746), "UL": (699, 716)},
        13: {"DL": (746, 756), "UL": (777, 787)},
        17: {"DL": (734, 746), "UL": (704, 716)},
        20: {"DL": (791, 821), "UL": (832, 862)},
        25: {"DL": (1930, 1995), "UL": (1850, 1915)},
        26: {"DL": (859, 894), "UL": (814, 849)},
        28: {"DL": (758, 803), "UL": (703, 748)},
        38: {"DL": (2570, 2620), "UL": (2570, 2620)},  # TDD
        40: {"DL": (2300, 2400), "UL": (2300, 2400)},  # TDD
        41: {"DL": (2496, 2690), "UL": (2496, 2690)},  # TDD
        66: {"DL": (2110, 2200), "UL": (1710, 1780)},
    }

    if band not in bands:
        raise ValueError(f"Unknown LTE band: {band}")

    return bands[band][direction.upper()]
