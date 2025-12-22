#!/usr/bin/env python3
"""
CMW500 LAN Query Application

Communicates with a Rohde & Schwarz CMW500 via LAN to query
the instrument's identification string using SCPI commands.
"""

import argparse
import socket
import sys

DEFAULT_PORT = 5025  # Standard SCPI-RAW port
DEFAULT_TIMEOUT = 5.0  # seconds


def query_cmw500_idn(host: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """
    Query the CMW500 instrument identification string.

    Args:
        host: IP address or hostname of the CMW500
        port: SCPI port (default 5025)
        timeout: Socket timeout in seconds

    Returns:
        The instrument identification string

    Raises:
        ConnectionError: If unable to connect to the instrument
        TimeoutError: If the connection times out
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))

            # Send the *IDN? query (SCPI standard identification query)
            command = "*IDN?\n"
            sock.sendall(command.encode("ascii"))

            # Receive the response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"\n" in chunk:
                    break

            return response.decode("ascii").strip()

    except socket.timeout as e:
        raise TimeoutError(f"Connection to {host}:{port} timed out") from e
    except socket.error as e:
        raise ConnectionError(f"Failed to connect to {host}:{port}: {e}") from e


def main():
    parser = argparse.ArgumentParser(
        description="Query CMW500 instrument identification via LAN"
    )
    parser.add_argument(
        "host",
        help="IP address or hostname of the CMW500"
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"SCPI port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Connection timeout in seconds (default: {DEFAULT_TIMEOUT})"
    )

    args = parser.parse_args()

    try:
        idn = query_cmw500_idn(args.host, args.port, args.timeout)
        print(f"Instrument ID: {idn}")
    except (ConnectionError, TimeoutError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
