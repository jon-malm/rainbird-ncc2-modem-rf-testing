#!/usr/bin/env python3
"""
CMW500 Test Framework CLI

Command-line interface for controlling CMW500 and running tests.

Usage:
    cmw500-cli connect <host> [options]
    cmw500-cli query <host> <command> [options]
    cmw500-cli run-test <config_file> [options]
    cmw500-cli lte-cell <host> --on|--off [options]
    cmw500-cli info <host> [options]
"""

import argparse
import sys
import json
import logging
from pathlib import Path
from typing import Optional

from .core.client import CMW500Client
from .core.config import Config
from .core.scpi import SCPIConnection, SCPIError
from .utils.logging_config import setup_logging


def cmd_info(args) -> int:
    """Show instrument information."""
    try:
        with CMW500Client(args.host, args.port, args.timeout) as client:
            info = client.get_system_info()
            print(f"Manufacturer:     {info.manufacturer}")
            print(f"Model:            {info.model}")
            print(f"Serial Number:    {info.serial_number}")
            print(f"Firmware Version: {info.firmware_version}")

            if info.options:
                print(f"\nInstalled Options:")
                for opt in info.options:
                    print(f"  - {opt}")

            if args.verbose:
                try:
                    temp = client.get_temperature()
                    print(f"\nTemperature: {temp}°C")
                except SCPIError:
                    pass

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_query(args) -> int:
    """Send SCPI query and display result."""
    try:
        with SCPIConnection(args.host, args.port, args.timeout) as conn:
            if args.command.endswith("?"):
                response = conn.query(args.command)
                print(response.value)
            else:
                conn.write(args.command)
                if args.wait:
                    conn.wait_for_completion()
                print("OK")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_lte_cell(args) -> int:
    """Control LTE cell state."""
    try:
        with CMW500Client(args.host, args.port, args.timeout) as client:
            if args.on:
                if args.band:
                    client.lte.configure_cell(
                        band=args.band,
                        bandwidth_mhz=args.bandwidth,
                    )
                if args.power is not None:
                    client.lte.set_dl_power(rs_epre_dbm=args.power)
                client.lte.cell_on()
                print("LTE cell is ON")
            elif args.off:
                client.lte.cell_off()
                print("LTE cell is OFF")
            else:
                state = client.lte.get_cell_state()
                print(f"LTE cell state: {state}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_measure(args) -> int:
    """Perform measurements."""
    try:
        with CMW500Client(args.host, args.port, args.timeout) as client:
            if args.type == "power":
                # General purpose power measurement
                client.gprf.configure_power_measurement(
                    frequency_mhz=args.frequency,
                    expected_power_dbm=args.expected_power,
                )
                result = client.gprf.measure_power()
                print(f"Power: {result.power_dbm:.2f} dBm")
                print(f"Min:   {result.min_power_dbm:.2f} dBm")
                print(f"Max:   {result.max_power_dbm:.2f} dBm")

            elif args.type == "tx":
                # LTE TX power measurement
                result = client.lte.measure_tx_power()
                print(f"PUSCH Power: {result.pusch_power_dbm:.2f} dBm")
                print(f"PUCCH Power: {result.pucch_power_dbm:.2f} dBm")

            elif args.type == "aclr":
                # ACLR measurement
                result = client.lte.measure_aclr()
                print(f"ACLR UTRA-1: {result['utra_minus_1']:.2f} dB")
                print(f"ACLR UTRA+1: {result['utra_plus_1']:.2f} dB")
                print(f"ACLR EUTRA-1: {result['eutra_minus_1']:.2f} dB")
                print(f"ACLR EUTRA+1: {result['eutra_plus_1']:.2f} dB")

            elif args.type == "evm":
                # EVM measurement
                result = client.lte.measure_evm()
                print(f"EVM RMS:  {result['evm_rms_percent']:.2f}%")
                print(f"EVM Peak: {result['evm_peak_percent']:.2f}%")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate(args) -> int:
    """Generate RF signal."""
    try:
        with CMW500Client(args.host, args.port, args.timeout) as client:
            if args.off:
                client.gprf.generator_off()
                print("RF generator OFF")
            else:
                client.gprf.configure_generator(
                    frequency_mhz=args.frequency,
                    power_dbm=args.power,
                    modulation=args.modulation,
                )
                client.gprf.generator_on()
                print(f"RF generator ON: {args.frequency} MHz, {args.power} dBm")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_run_test(args) -> int:
    """Run test from configuration file."""
    try:
        # Load configuration
        config = Config.from_file(args.config)
        print(f"Loaded config from: {args.config}")

        with CMW500Client.from_config(config) as client:
            print(f"Connected to: {client.get_identification()}")

            # Configure LTE cell if specified
            if hasattr(config, 'lte') and config.lte:
                print("Configuring LTE cell...")
                client.lte.configure_from_config()

                if args.start_cell:
                    print("Starting cell...")
                    client.lte.cell_on()

                    if args.wait_attach:
                        print("Waiting for UE to attach...")
                        client.lte.wait_for_attach(timeout=args.attach_timeout)
                        print("UE attached!")

            print("Test complete")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_scenario(args) -> int:
    """Load and run network simulation scenario."""
    try:
        from .applications.network_simulation import NetworkSimulator

        with CMW500Client(args.host, args.port, args.timeout) as client:
            sim = NetworkSimulator(client)

            # Load predefined scenario
            if args.scenario == "static":
                scenario = NetworkSimulator.scenario_static_indoor()
            elif args.scenario == "pedestrian":
                scenario = NetworkSimulator.scenario_pedestrian()
            elif args.scenario == "vehicular":
                scenario = NetworkSimulator.scenario_vehicular()
            elif args.scenario == "highspeed":
                scenario = NetworkSimulator.scenario_high_speed()
            elif args.scenario == "urban":
                scenario = NetworkSimulator.scenario_urban_macro()
            else:
                print(f"Unknown scenario: {args.scenario}", file=sys.stderr)
                return 1

            print(f"Loading scenario: {scenario.name}")
            print(f"Description: {scenario.description}")

            sim.load_scenario(scenario)

            if args.enable_fading:
                sim.enable_fading()
                print("Fading enabled")

            if args.start_cell:
                client.lte.cell_on()
                print("Cell started")

            print("Scenario loaded successfully")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_config_gen(args) -> int:
    """Generate sample configuration file."""
    try:
        config = Config()
        config._raw_config["instrument"] = {"host": args.host or "192.168.1.100"}

        output_path = args.output or "cmw500_config.yaml"
        config.save(output_path)
        print(f"Sample configuration saved to: {output_path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="cmw500-cli",
        description="CMW500 Test Framework CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # info command
    info_parser = subparsers.add_parser("info", help="Show instrument information")
    info_parser.add_argument("host", help="CMW500 IP address")
    info_parser.add_argument("-p", "--port", type=int, default=5025)
    info_parser.add_argument("-t", "--timeout", type=float, default=10.0)
    info_parser.set_defaults(func=cmd_info)

    # query command
    query_parser = subparsers.add_parser("query", help="Send SCPI query")
    query_parser.add_argument("host", help="CMW500 IP address")
    query_parser.add_argument("scpi_command", dest="command", help="SCPI command")
    query_parser.add_argument("-p", "--port", type=int, default=5025)
    query_parser.add_argument("-t", "--timeout", type=float, default=10.0)
    query_parser.add_argument("-w", "--wait", action="store_true",
                              help="Wait for operation complete")
    query_parser.set_defaults(func=cmd_query)

    # lte-cell command
    lte_parser = subparsers.add_parser("lte-cell", help="Control LTE cell")
    lte_parser.add_argument("host", help="CMW500 IP address")
    lte_group = lte_parser.add_mutually_exclusive_group()
    lte_group.add_argument("--on", action="store_true", help="Turn cell on")
    lte_group.add_argument("--off", action="store_true", help="Turn cell off")
    lte_parser.add_argument("-b", "--band", type=int, help="LTE band")
    lte_parser.add_argument("--bandwidth", type=float, default=10.0,
                            help="Channel bandwidth (MHz)")
    lte_parser.add_argument("--power", type=float, help="RS EPRE power (dBm)")
    lte_parser.add_argument("-p", "--port", type=int, default=5025)
    lte_parser.add_argument("-t", "--timeout", type=float, default=10.0)
    lte_parser.set_defaults(func=cmd_lte_cell)

    # measure command
    meas_parser = subparsers.add_parser("measure", help="Perform measurements")
    meas_parser.add_argument("host", help="CMW500 IP address")
    meas_parser.add_argument("type", choices=["power", "tx", "aclr", "evm"],
                             help="Measurement type")
    meas_parser.add_argument("-f", "--frequency", type=float, default=1950.0,
                             help="Frequency (MHz)")
    meas_parser.add_argument("--expected-power", type=float, default=-30.0,
                             help="Expected power (dBm)")
    meas_parser.add_argument("-p", "--port", type=int, default=5025)
    meas_parser.add_argument("-t", "--timeout", type=float, default=10.0)
    meas_parser.set_defaults(func=cmd_measure)

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate RF signal")
    gen_parser.add_argument("host", help="CMW500 IP address")
    gen_parser.add_argument("-f", "--frequency", type=float, default=1950.0,
                            help="Frequency (MHz)")
    gen_parser.add_argument("--power", type=float, default=-30.0,
                            help="Power (dBm)")
    gen_parser.add_argument("-m", "--modulation", default="CW",
                            choices=["CW", "AM", "FM"],
                            help="Modulation type")
    gen_parser.add_argument("--off", action="store_true",
                            help="Turn generator off")
    gen_parser.add_argument("-p", "--port", type=int, default=5025)
    gen_parser.add_argument("-t", "--timeout", type=float, default=10.0)
    gen_parser.set_defaults(func=cmd_generate)

    # run-test command
    test_parser = subparsers.add_parser("run-test", help="Run test from config")
    test_parser.add_argument("config", help="Configuration file path")
    test_parser.add_argument("--start-cell", action="store_true",
                             help="Start cell after configuration")
    test_parser.add_argument("--wait-attach", action="store_true",
                             help="Wait for UE to attach")
    test_parser.add_argument("--attach-timeout", type=float, default=60.0,
                             help="Attach timeout (seconds)")
    test_parser.set_defaults(func=cmd_run_test)

    # scenario command
    scen_parser = subparsers.add_parser("scenario",
                                         help="Load network simulation scenario")
    scen_parser.add_argument("host", help="CMW500 IP address")
    scen_parser.add_argument("scenario",
                             choices=["static", "pedestrian", "vehicular",
                                      "highspeed", "urban"],
                             help="Scenario name")
    scen_parser.add_argument("--enable-fading", action="store_true",
                             help="Enable fading channel")
    scen_parser.add_argument("--start-cell", action="store_true",
                             help="Start cell after loading")
    scen_parser.add_argument("-p", "--port", type=int, default=5025)
    scen_parser.add_argument("-t", "--timeout", type=float, default=10.0)
    scen_parser.set_defaults(func=cmd_scenario)

    # config-gen command
    cfg_parser = subparsers.add_parser("config-gen",
                                        help="Generate sample config file")
    cfg_parser.add_argument("--host", help="CMW500 IP address for config")
    cfg_parser.add_argument("-o", "--output", help="Output file path")
    cfg_parser.set_defaults(func=cmd_config_gen)

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(level=args.log_level, console=args.verbose)

    if not args.command:
        parser.print_help()
        return 1

    # Handle query command argument naming
    if args.command == "query" and hasattr(args, 'scpi_command'):
        args.command_str = args.scpi_command

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
