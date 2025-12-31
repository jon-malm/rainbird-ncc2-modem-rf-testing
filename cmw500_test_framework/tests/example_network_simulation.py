#!/usr/bin/env python3
"""
Example Network Simulation Test Script

Demonstrates how to use the CMW500 test framework for network simulation:
1. Configure fading channels
2. Load predefined scenarios
3. Run SNR sweep tests
4. Simulate different mobility conditions

Usage:
    python example_network_simulation.py <CMW500_IP> [--scenario <name>]
"""

import argparse
import sys
import time

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from cmw500_test_framework import CMW500Client
from cmw500_test_framework.applications.network_simulation import (
    NetworkSimulator,
    FadingProfile,
    CorrelationType,
    NetworkScenario,
    FadingConfig,
    CellConfig,
)
from cmw500_test_framework.utils.logging_config import setup_logging
from cmw500_test_framework.utils.helpers import doppler_from_speed, speed_from_doppler


def test_fading_profiles(host: str):
    """
    Test different fading profiles and measure impact.

    Cycles through various fading profiles and shows their characteristics.
    """
    logger = setup_logging(level="INFO")

    profiles = [
        ("STATIC", "No fading - static channel"),
        ("EPA5", "Extended Pedestrian A, 5 Hz Doppler (~3 km/h)"),
        ("EVA5", "Extended Vehicular A, 5 Hz Doppler"),
        ("EVA70", "Extended Vehicular A, 70 Hz Doppler (~40 km/h)"),
        ("ETU70", "Extended Typical Urban, 70 Hz Doppler"),
        ("ETU300", "Extended Typical Urban, 300 Hz Doppler (~180 km/h)"),
    ]

    print("\nFading Profile Test")
    print("=" * 60)

    with CMW500Client(host) as client:
        sim = NetworkSimulator(client)

        # Configure basic cell
        client.lte.configure_cell(band=1, bandwidth_mhz=10)
        client.lte.set_dl_power(rs_epre_dbm=-85)
        client.lte.cell_on()

        print("\nWaiting for UE to attach...")
        try:
            client.lte.wait_for_attach(timeout=60)
        except TimeoutError:
            print("UE attachment timeout - continuing with profiles anyway")

        for profile_name, description in profiles:
            print(f"\n{'-' * 60}")
            print(f"Profile: {profile_name}")
            print(f"Description: {description}")

            # Configure fading
            sim.configure_fading(profile=profile_name, correlation="LOW")
            sim.enable_fading()

            # Let it run for a moment
            time.sleep(3)

            # Check connection state
            state = client.lte.get_connection_state()
            print(f"Connection state: {state}")

            sim.disable_fading()
            time.sleep(1)

        client.lte.cell_off()

    print("\n" + "=" * 60)
    print("Fading profile test complete")


def test_snr_sensitivity(host: str, snr_min: float = 0, snr_max: float = 30):
    """
    Test SNR sensitivity by sweeping AWGN noise level.

    Args:
        host: CMW500 IP address
        snr_min: Minimum SNR (dB)
        snr_max: Maximum SNR (dB)
    """
    logger = setup_logging(level="INFO")

    print("\nSNR Sensitivity Test")
    print("=" * 60)

    with CMW500Client(host) as client:
        sim = NetworkSimulator(client)

        # Configure cell
        client.lte.configure_cell(band=1, bandwidth_mhz=10)
        client.lte.set_dl_power(rs_epre_dbm=-85)
        client.lte.cell_on()

        print("Waiting for UE to attach...")
        try:
            client.lte.wait_for_attach(timeout=60)
        except TimeoutError:
            print("UE attachment timeout")
            return

        # Run SNR sweep
        print(f"\nSweeping SNR from {snr_max} to {snr_min} dB...")
        print(f"{'SNR (dB)':>10} | {'Status':>12} | {'Notes'}")
        print("-" * 50)

        def check_at_snr(snr):
            state = client.lte.get_connection_state()
            connected = "CEST" in state or "ATT" in state
            return {"connected": connected, "state": state}

        results = sim.snr_sweep(
            start_snr_db=snr_max,
            end_snr_db=snr_min,
            steps=7,
            step_delay_s=3,
            callback=check_at_snr,
        )

        for snr, result in results:
            status = "Connected" if result["connected"] else "Dropped"
            print(f"{snr:>10.1f} | {status:>12} | {result['state'][:20]}")

        # Find approximate threshold
        threshold = None
        for i, (snr, result) in enumerate(results):
            if not result["connected"]:
                if i > 0:
                    threshold = (results[i-1][0] + snr) / 2
                else:
                    threshold = snr
                break

        print(f"\nApproximate SNR threshold: {threshold:.1f} dB" if threshold else
              "UE maintained connection through entire sweep")

        sim.configure_awgn(enabled=False)
        client.lte.cell_off()


def test_mobility_scenarios(host: str):
    """
    Test predefined mobility scenarios.
    """
    logger = setup_logging(level="INFO")

    print("\nMobility Scenario Test")
    print("=" * 60)

    scenarios = [
        NetworkSimulator.scenario_static_indoor(),
        NetworkSimulator.scenario_pedestrian(),
        NetworkSimulator.scenario_vehicular(),
        NetworkSimulator.scenario_high_speed(),
    ]

    with CMW500Client(host) as client:
        sim = NetworkSimulator(client)

        for scenario in scenarios:
            print(f"\n{'-' * 60}")
            print(f"Scenario: {scenario.name}")
            print(f"Description: {scenario.description}")

            if scenario.fading:
                profile = scenario.fading.profile
                if isinstance(profile, FadingProfile):
                    profile = profile.value
                print(f"Fading profile: {profile}")

            print(f"Path loss: {scenario.path_loss_db} dB")

            # Load and test scenario
            sim.load_scenario(scenario)

            if scenario.fading and scenario.fading.profile != FadingProfile.STATIC:
                sim.enable_fading()

            client.lte.cell_on()

            # Check connection after cell is on
            time.sleep(5)
            state = client.lte.get_connection_state()
            print(f"Cell state after scenario load: {state}")

            # Reset for next scenario
            sim.reset_to_default()
            client.lte.cell_off()
            time.sleep(2)

    print("\n" + "=" * 60)
    print("Mobility scenario test complete")


def test_custom_scenario(host: str):
    """
    Demonstrate creating a custom network scenario.
    """
    print("\nCustom Scenario Test")
    print("=" * 60)

    # Create custom scenario
    custom_scenario = NetworkScenario(
        name="Custom Urban Mobility",
        description="Custom scenario for urban environment at 30 km/h",
        cells=[
            CellConfig(
                cell_id=1,
                band=7,  # Band 7 (2.6 GHz)
                frequency_mhz=2650.0,
                power_dbm=-80.0,
            ),
        ],
        fading=FadingConfig(
            profile=FadingProfile.EVA70,
            correlation=CorrelationType.LOW,
            awgn_enabled=True,
            awgn_snr_db=25.0,
        ),
        path_loss_db=75.0,
    )

    # Calculate expected Doppler for reference
    speed_kmh = 30
    doppler = doppler_from_speed(speed_kmh, 2650)
    print(f"Custom scenario: {custom_scenario.name}")
    print(f"Expected Doppler at {speed_kmh} km/h @ 2650 MHz: {doppler:.1f} Hz")

    with CMW500Client(host) as client:
        sim = NetworkSimulator(client)

        print("\nLoading custom scenario...")
        sim.load_scenario(custom_scenario)

        # Enable fading
        sim.enable_fading()
        print("Fading enabled")

        # Start cell
        client.lte.cell_on()
        print("Cell started")

        # Run for a while
        print("\nRunning scenario for 10 seconds...")
        time.sleep(10)

        # Get status
        state = client.lte.get_connection_state()
        print(f"Final connection state: {state}")

        # Cleanup
        sim.reset_to_default()
        client.lte.cell_off()

    print("\nCustom scenario test complete")


def main():
    parser = argparse.ArgumentParser(description="Network Simulation Example")
    parser.add_argument("host", help="CMW500 IP address")
    parser.add_argument(
        "--test",
        choices=["fading", "snr", "mobility", "custom", "all"],
        default="all",
        help="Test to run"
    )
    parser.add_argument("--snr-min", type=float, default=0,
                        help="Minimum SNR for sweep (dB)")
    parser.add_argument("--snr-max", type=float, default=30,
                        help="Maximum SNR for sweep (dB)")

    args = parser.parse_args()

    print("CMW500 Network Simulation Test")
    print("=" * 60)
    print(f"Host: {args.host}")
    print(f"Test: {args.test}")

    if args.test in ("fading", "all"):
        test_fading_profiles(args.host)

    if args.test in ("snr", "all"):
        test_snr_sensitivity(args.host, args.snr_min, args.snr_max)

    if args.test in ("mobility", "all"):
        test_mobility_scenarios(args.host)

    if args.test in ("custom", "all"):
        test_custom_scenario(args.host)

    print("\n" + "=" * 60)
    print("All tests complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
