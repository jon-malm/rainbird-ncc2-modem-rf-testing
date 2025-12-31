#!/usr/bin/env python3
"""
Example RF Measurement Script

Demonstrates general purpose RF measurements with the CMW500:
1. RF signal generation
2. Power measurements
3. Spectrum analysis
4. Frequency measurements

Usage:
    python example_rf_measurement.py <CMW500_IP>
"""

import argparse
import sys
import time

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from cmw500_test_framework import CMW500Client
from cmw500_test_framework.utils.logging_config import setup_logging
from cmw500_test_framework.utils.helpers import format_frequency, format_power


def test_cw_generation(host: str, frequency_mhz: float = 1950.0, power_dbm: float = -30.0):
    """
    Test CW signal generation.

    Args:
        host: CMW500 IP address
        frequency_mhz: Output frequency in MHz
        power_dbm: Output power in dBm
    """
    print("\nCW Signal Generation Test")
    print("=" * 60)

    with CMW500Client(host) as client:
        gprf = client.gprf

        print(f"Configuring generator: {format_frequency(frequency_mhz * 1e6)}, "
              f"{format_power(power_dbm)}")

        # Configure generator
        gprf.configure_generator(
            frequency_mhz=frequency_mhz,
            power_dbm=power_dbm,
            modulation="CW",
        )

        # Turn on
        gprf.generator_on()
        print("Generator ON")

        # Verify settings
        settings = gprf.get_generator_settings()
        print(f"Verified frequency: {format_frequency(settings['frequency_mhz'] * 1e6)}")
        print(f"Verified power: {format_power(settings['power_dbm'])}")

        # Run for a few seconds
        print("\nSignal active for 5 seconds...")
        time.sleep(5)

        # Turn off
        gprf.generator_off()
        print("Generator OFF")

    print("CW generation test complete")


def test_power_measurement(host: str, frequency_mhz: float = 1950.0):
    """
    Test power measurement capabilities.

    Args:
        host: CMW500 IP address
        frequency_mhz: Measurement frequency
    """
    print("\nPower Measurement Test")
    print("=" * 60)

    with CMW500Client(host) as client:
        gprf = client.gprf

        print(f"Configuring measurement at {format_frequency(frequency_mhz * 1e6)}")

        # Configure measurement
        gprf.configure_power_measurement(
            frequency_mhz=frequency_mhz,
            expected_power_dbm=-30.0,
        )

        # Auto-level
        print("Running auto-level...")
        detected_power = gprf.auto_level()
        print(f"Auto-detected power: {format_power(detected_power)}")

        # Perform measurement
        print("\nPerforming power measurement...")
        result = gprf.measure_power()

        print(f"Reliability: {result.reliability}")
        print(f"Average power: {format_power(result.power_dbm)}")
        print(f"Minimum: {format_power(result.min_power_dbm)}")
        print(f"Maximum: {format_power(result.max_power_dbm)}")
        print(f"Std dev: {result.std_dev:.2f} dB")

        # Multiple measurements
        print("\nRunning 10 continuous measurements...")
        powers = gprf.measure_power_continuous(count=10, interval_ms=200)

        if powers:
            avg = sum(powers) / len(powers)
            min_p = min(powers)
            max_p = max(powers)
            print(f"Average: {format_power(avg)}")
            print(f"Range: {format_power(min_p)} to {format_power(max_p)}")
            print(f"Spread: {max_p - min_p:.2f} dB")

    print("Power measurement test complete")


def test_spectrum_measurement(
    host: str,
    center_freq_mhz: float = 1950.0,
    span_mhz: float = 20.0,
):
    """
    Test spectrum analysis capabilities.

    Args:
        host: CMW500 IP address
        center_freq_mhz: Center frequency
        span_mhz: Frequency span
    """
    print("\nSpectrum Measurement Test")
    print("=" * 60)

    with CMW500Client(host) as client:
        gprf = client.gprf

        print(f"Configuring spectrum analysis:")
        print(f"  Center: {format_frequency(center_freq_mhz * 1e6)}")
        print(f"  Span: {span_mhz} MHz")

        # Configure spectrum measurement
        gprf.configure_spectrum_measurement(
            center_frequency_mhz=center_freq_mhz,
            span_mhz=span_mhz,
            rbw_khz=30.0,
            vbw_khz=100.0,
        )

        # Measure
        print("\nPerforming spectrum measurement...")
        result = gprf.measure_spectrum_peak()

        print(f"Reliability: {result.reliability}")
        print(f"Peak frequency: {format_frequency(result.center_frequency_hz)}")
        print(f"Peak power: {format_power(result.peak_power_dbm)}")
        print(f"Channel power: {format_power(result.channel_power_dbm)}")

    print("Spectrum measurement test complete")


def test_frequency_measurement(host: str):
    """
    Test frequency measurement capabilities.

    Args:
        host: CMW500 IP address
    """
    print("\nFrequency Measurement Test")
    print("=" * 60)

    with CMW500Client(host) as client:
        gprf = client.gprf

        # Configure for expected frequency range
        gprf.configure_power_measurement(
            frequency_mhz=1950.0,
            expected_power_dbm=-30.0,
        )

        # Measure frequency
        print("Measuring signal frequency...")
        result = gprf.measure_frequency()

        print(f"Reliability: {result['reliability']}")
        print(f"Frequency: {format_frequency(result['frequency_hz'])}")
        print(f"Error: {result['frequency_error_hz']:.1f} Hz")

    print("Frequency measurement test complete")


def test_loopback(host: str, frequency_mhz: float = 1950.0, power_dbm: float = -30.0):
    """
    Test internal loopback - generate and measure same signal.

    This requires proper RF routing/cabling.

    Args:
        host: CMW500 IP address
        frequency_mhz: Test frequency
        power_dbm: Test power level
    """
    print("\nLoopback Test")
    print("=" * 60)
    print("Note: Requires RF cable from generator output to analyzer input")

    with CMW500Client(host) as client:
        gprf = client.gprf

        # Configure generator
        print(f"\nConfiguring generator: {format_frequency(frequency_mhz * 1e6)}, "
              f"{format_power(power_dbm)}")
        gprf.configure_generator(
            frequency_mhz=frequency_mhz,
            power_dbm=power_dbm,
            modulation="CW",
        )
        gprf.generator_on()

        # Configure measurement
        print("Configuring analyzer...")
        gprf.configure_power_measurement(
            frequency_mhz=frequency_mhz,
            expected_power_dbm=power_dbm,
        )

        time.sleep(1)

        # Measure
        print("\nMeasuring loopback signal...")
        result = gprf.measure_power()

        print(f"\nResults:")
        print(f"  Generated: {format_power(power_dbm)}")
        print(f"  Measured:  {format_power(result.power_dbm)}")
        print(f"  Difference: {result.power_dbm - power_dbm:.2f} dB")

        # Frequency accuracy
        freq_result = gprf.measure_frequency()
        freq_error_ppm = (freq_result['frequency_error_hz'] / (frequency_mhz * 1e6)) * 1e6
        print(f"  Freq error: {freq_result['frequency_error_hz']:.1f} Hz ({freq_error_ppm:.3f} ppm)")

        # Cleanup
        gprf.generator_off()

    print("\nLoopback test complete")


def main():
    parser = argparse.ArgumentParser(description="RF Measurement Example")
    parser.add_argument("host", help="CMW500 IP address")
    parser.add_argument(
        "--test",
        choices=["cw", "power", "spectrum", "frequency", "loopback", "all"],
        default="all",
        help="Test to run"
    )
    parser.add_argument("-f", "--frequency", type=float, default=1950.0,
                        help="Test frequency (MHz)")
    parser.add_argument("-p", "--power", type=float, default=-30.0,
                        help="Test power (dBm)")

    args = parser.parse_args()

    print("CMW500 RF Measurement Test")
    print("=" * 60)
    print(f"Host: {args.host}")
    print(f"Test: {args.test}")

    if args.test in ("cw", "all"):
        test_cw_generation(args.host, args.frequency, args.power)

    if args.test in ("power", "all"):
        test_power_measurement(args.host, args.frequency)

    if args.test in ("spectrum", "all"):
        test_spectrum_measurement(args.host, args.frequency)

    if args.test in ("frequency", "all"):
        test_frequency_measurement(args.host)

    if args.test in ("loopback", "all"):
        test_loopback(args.host, args.frequency, args.power)

    print("\n" + "=" * 60)
    print("All tests complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
