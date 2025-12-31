#!/usr/bin/env python3
"""
Example LTE Test Script

Demonstrates how to use the CMW500 test framework to:
1. Connect to CMW500
2. Configure LTE cell
3. Wait for UE attachment
4. Perform measurements
5. Report results

Usage:
    python example_lte_test.py <CMW500_IP>
"""

import argparse
import sys
import time
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from cmw500_test_framework import CMW500Client
from cmw500_test_framework.core.config import Config
from cmw500_test_framework.utils.logging_config import setup_logging


def run_lte_basic_test(
    host: str,
    band: int = 1,
    bandwidth_mhz: float = 10.0,
    power_dbm: float = -85.0,
) -> Dict[str, any]:
    """
    Run basic LTE signaling test.

    Args:
        host: CMW500 IP address
        band: LTE band number
        bandwidth_mhz: Channel bandwidth
        power_dbm: DL power level

    Returns:
        Dictionary with test results
    """
    results = {
        "status": "FAIL",
        "errors": [],
        "measurements": {},
    }

    logger = setup_logging(level="INFO")
    logger.info(f"Starting LTE basic test - Band {band}, BW {bandwidth_mhz} MHz")

    try:
        with CMW500Client(host) as client:
            # Get instrument info
            info = client.get_system_info()
            results["instrument"] = {
                "model": info.model,
                "serial": info.serial_number,
                "firmware": info.firmware_version,
            }
            logger.info(f"Connected to {info.model} (S/N: {info.serial_number})")

            # Reset to clean state
            logger.info("Resetting instrument...")
            client.reset()
            time.sleep(2)

            # Configure LTE cell
            logger.info(f"Configuring LTE cell: Band {band}, {bandwidth_mhz} MHz")
            client.lte.configure_cell(
                band=band,
                bandwidth_mhz=bandwidth_mhz,
            )

            # Set power levels
            logger.info(f"Setting DL power: {power_dbm} dBm")
            client.lte.set_dl_power(rs_epre_dbm=power_dbm)

            # Turn on cell
            logger.info("Turning on LTE cell...")
            client.lte.cell_on()

            # Check cell state
            cell_state = client.lte.get_cell_state()
            logger.info(f"Cell state: {cell_state}")

            if cell_state != "ON":
                results["errors"].append(f"Cell failed to turn on: {cell_state}")
                return results

            results["cell_configured"] = True

            # Wait for UE attachment (with timeout)
            logger.info("Waiting for UE to attach (60s timeout)...")
            try:
                client.lte.wait_for_attach(timeout=60)
                results["ue_attached"] = True
                logger.info("UE attached successfully")

                # Perform measurements
                logger.info("Performing TX power measurement...")
                tx_power = client.lte.measure_tx_power()
                results["measurements"]["tx_power"] = {
                    "pusch_dbm": tx_power.pusch_power_dbm,
                    "pucch_dbm": tx_power.pucch_power_dbm,
                    "reliability": tx_power.reliability,
                }
                logger.info(f"PUSCH Power: {tx_power.pusch_power_dbm:.1f} dBm")

                # ACLR measurement
                logger.info("Performing ACLR measurement...")
                aclr = client.lte.measure_aclr()
                results["measurements"]["aclr"] = aclr
                logger.info(f"ACLR EUTRA-1: {aclr['eutra_minus_1']:.1f} dB")

                # EVM measurement
                logger.info("Performing EVM measurement...")
                evm = client.lte.measure_evm()
                results["measurements"]["evm"] = evm
                logger.info(f"EVM RMS: {evm['evm_rms_percent']:.2f}%")

                results["status"] = "PASS"

            except TimeoutError:
                logger.warning("UE did not attach within timeout")
                results["ue_attached"] = False
                results["errors"].append("UE attachment timeout")

            # Turn off cell
            logger.info("Turning off LTE cell...")
            client.lte.cell_off()

    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        results["errors"].append(str(e))

    return results


def run_lte_power_sweep(
    host: str,
    band: int = 1,
    power_start: float = -50.0,
    power_end: float = -100.0,
    power_step: float = 5.0,
) -> List[Dict]:
    """
    Run power sweep test - measure UE performance at different DL power levels.

    Args:
        host: CMW500 IP address
        band: LTE band
        power_start: Starting power (dBm)
        power_end: Ending power (dBm)
        power_step: Step size (dB)

    Returns:
        List of measurement results at each power level
    """
    logger = setup_logging(level="INFO")
    results = []

    with CMW500Client(host) as client:
        # Configure cell
        client.lte.configure_cell(band=band)
        client.lte.set_dl_power(rs_epre_dbm=power_start)
        client.lte.cell_on()

        # Wait for initial attach
        try:
            client.lte.wait_for_attach(timeout=60)
        except TimeoutError:
            logger.error("Initial UE attachment failed")
            return results

        # Power sweep
        power = power_start
        while power >= power_end:
            logger.info(f"Testing at {power:.0f} dBm...")

            # Set new power level
            client.lte.set_dl_power(rs_epre_dbm=power)
            time.sleep(2)  # Allow settling

            # Check if still connected
            state = client.lte.get_connection_state()

            measurement = {
                "power_dbm": power,
                "connected": "CEST" in state or "ATT" in state,
            }

            if measurement["connected"]:
                try:
                    tx = client.lte.measure_tx_power()
                    measurement["tx_power_dbm"] = tx.pusch_power_dbm
                except Exception:
                    measurement["tx_power_dbm"] = None

            results.append(measurement)
            logger.info(f"  Connected: {measurement['connected']}")

            power -= power_step

        client.lte.cell_off()

    return results


def main():
    parser = argparse.ArgumentParser(description="LTE Test Example")
    parser.add_argument("host", help="CMW500 IP address")
    parser.add_argument("-b", "--band", type=int, default=1, help="LTE band")
    parser.add_argument("--bandwidth", type=float, default=10.0,
                        help="Channel bandwidth (MHz)")
    parser.add_argument("-p", "--power", type=float, default=-85.0,
                        help="DL power (dBm)")
    parser.add_argument("--sweep", action="store_true",
                        help="Run power sweep test instead")

    args = parser.parse_args()

    if args.sweep:
        print("Running power sweep test...")
        results = run_lte_power_sweep(args.host, args.band)
        print("\nPower Sweep Results:")
        print("-" * 50)
        for r in results:
            status = "Connected" if r["connected"] else "Disconnected"
            tx = f"{r.get('tx_power_dbm', 'N/A')}" if r.get('tx_power_dbm') else "N/A"
            print(f"  {r['power_dbm']:6.0f} dBm: {status:12} TX: {tx}")
    else:
        print("Running basic LTE test...")
        results = run_lte_basic_test(
            args.host,
            band=args.band,
            bandwidth_mhz=args.bandwidth,
            power_dbm=args.power,
        )

        print("\n" + "=" * 50)
        print(f"Test Result: {results['status']}")
        print("=" * 50)

        if results.get("instrument"):
            print(f"Instrument: {results['instrument']['model']}")

        if results.get("measurements"):
            print("\nMeasurements:")
            for name, data in results["measurements"].items():
                print(f"  {name}: {data}")

        if results.get("errors"):
            print("\nErrors:")
            for err in results["errors"]:
                print(f"  - {err}")

    return 0 if results.get("status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
