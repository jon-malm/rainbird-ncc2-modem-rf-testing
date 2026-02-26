#!/usr/bin/env python3
"""eSIM setup utility for the NCC2 modem test framework.

Provisions and manages eSIM profiles on the Quectel EG21-G modem so that
the test suite's multi-profile tests (e.g. test_profile_switch_timing)
can execute.

Supports both Quectel vendor-specific AT+QESIM commands and 3GPP-standard
APDU sequences (AT+CCHO/CGLA/CCHC) for identifier retrieval.

Usage:
    uv run python tools/esim_setup.py info
    uv run python tools/esim_setup.py list
    uv run python tools/esim_setup.py download <activation-code>
    uv run python tools/esim_setup.py enable <iccid>
    uv run python tools/esim_setup.py disable <iccid>
    uv run python tools/esim_setup.py delete <iccid>
    uv run python tools/esim_setup.py verify

Reference:
    Quectel EC25 Series & EG21-G eSIM AT Commands Manual V1.0.0
    GSMA SGP.22 RSP Technical Specification
    FW-NCC2 Provisioning and Cloud Connectivity Plan, Appendix A
"""

import argparse
import re
import sys
import time
from pathlib import Path

# Allow importing modem_interface from the project root
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from modem_interface import EG21GModemManager  # noqa: E402

# ISD-R AID defined by GSMA SGP.22 for eUICC access
ISD_R_AID = "A0000005591010FFFFFFFF8900000100"

# APDU: GET DATA for EID (tag 5A per GSMA SGP.22)
GET_EID_APDU = "80CA005A00"

# AT command timeout for standard queries (seconds)
CMD_TIMEOUT = 5

# AT command timeout for profile operations (seconds)
PROFILE_OP_TIMEOUT = 30

# AT command timeout for OTA download (seconds)
OTA_TIMEOUT = 120


def connect_modem(port: str | None = None) -> EG21GModemManager:
    """Connect to the modem, auto-detecting the port if not specified."""
    modem = EG21GModemManager()
    if port:
        if not modem.connect(port):
            print(f"ERROR: Failed to connect on {port}")
            sys.exit(1)
    else:
        detected = modem.find_at_port()
        if not detected:
            print("ERROR: No Quectel modem detected")
            sys.exit(1)
        if not modem.connect(detected):
            print(f"ERROR: Failed to connect on {detected}")
            sys.exit(1)
    print(f"Connected: {modem.port}")
    return modem


def get_eid_via_apdu(modem: EG21GModemManager) -> str | None:
    """Retrieve eUICC ID using 3GPP-standard APDU sequence.

    Sequence (per FW-NCC2 Provisioning Plan, Appendix A):
      1. AT+CCHO="<ISD-R AID>"  → open logical channel
      2. AT+CGLA=<sid>,10,"80CA005A00"  → GET DATA for EID
      3. AT+CCHC=<sid>  → close channel

    Returns:
        32-digit EID string, or None on failure.
    """
    # Step 1: Open logical channel to ISD-R
    resp = modem.send_command(f'AT+CCHO="{ISD_R_AID}"', timeout=CMD_TIMEOUT)
    match = re.search(r"\+CCHO:\s*(\d+)", resp)
    if not match:
        print(f"  APDU: Failed to open logical channel: {resp}")
        return None
    session_id = match.group(1)

    try:
        # Step 2: GET DATA for EID
        resp = modem.send_command(
            f'AT+CGLA={session_id},10,"{GET_EID_APDU}"',
            timeout=CMD_TIMEOUT,
        )
        match = re.search(r'\+CGLA:\s*\d+,"([0-9A-Fa-f]+)"', resp)
        if not match:
            print(f"  APDU: Failed to read EID: {resp}")
            return None

        data = match.group(1).upper()

        # Parse TLV: tag=5A, length=10 (16 bytes), then 32 hex chars, then SW 9000
        if not data.startswith("5A10"):
            print(f"  APDU: Unexpected EID tag/length: {data[:4]}")
            return None

        # Status word check
        status_word = data[-4:]
        if status_word != "9000":
            print(f"  APDU: Error status word: {status_word}")
            return None

        # EID is 32 hex chars between the TLV header and status word
        eid = data[4:-4]
        if len(eid) != 32:
            print(f"  APDU: EID length {len(eid)} != 32: {eid}")
            return None

        return eid
    finally:
        # Step 3: Always close the logical channel
        modem.send_command(f"AT+CCHC={session_id}", timeout=CMD_TIMEOUT)


def get_eid_via_qesim(modem: EG21GModemManager) -> str | None:
    """Retrieve eUICC ID using Quectel vendor-specific AT+QESIM="eid".

    Returns:
        EID string, or None if command not supported.
    """
    resp = modem.send_command('AT+QESIM="eid"', timeout=CMD_TIMEOUT)
    if "ERROR" in resp:
        return None
    match = re.search(r'\+QESIM:\s*"eid",(\d{32})', resp)
    if match:
        return match.group(1)
    # Some firmware formats differ — try a looser match
    match = re.search(r"(\d{32})", resp)
    return match.group(1) if match else None


def get_iccid(modem: EG21GModemManager) -> str | None:
    """Read the active profile's ICCID via AT+CRSM (3GPP-standard).

    Reads EF_ICCID (file ID 0x2FE2 = 12258 decimal).
    """
    resp = modem.send_command("AT+CRSM=176,12258,0,0,10", timeout=CMD_TIMEOUT)
    match = re.search(r"\+CRSM:\s*\d+,\d+,\"([0-9A-Fa-f]+)\"", resp)
    if not match:
        return None
    raw = match.group(1)
    # ICCID is BCD-encoded with nibble swapping — decode
    iccid = ""
    for i in range(0, len(raw), 2):
        iccid += raw[i + 1] + raw[i]
    # Strip trailing F padding
    return iccid.rstrip("Ff")


def get_imsi(modem: EG21GModemManager) -> str | None:
    """Read the active profile's IMSI via AT+CIMI."""
    resp = modem.send_command("AT+CIMI", timeout=CMD_TIMEOUT)
    match = re.search(r"(\d{10,15})", resp)
    return match.group(1) if match else None


def cmd_info(modem: EG21GModemManager) -> None:
    """Display modem and eSIM identity information."""
    print("\n--- Modem Info ---")
    info = modem.get_modem_info()
    for key, value in info.items():
        print(f"  {key}: {value}")

    print("\n--- SIM Status ---")
    sim_status = modem.get_sim_status()
    print(f"  AT+CPIN: {sim_status}")

    print("\n--- Active Profile ---")
    iccid = get_iccid(modem)
    imsi = get_imsi(modem)
    print(f"  ICCID: {iccid or 'N/A'}")
    print(f"  IMSI:  {imsi or 'N/A'}")

    print("\n--- eUICC ID ---")
    # Try 3GPP-standard APDU first (vendor-neutral)
    eid = get_eid_via_apdu(modem)
    if eid:
        print(f"  EID (APDU): {eid}")
    else:
        print("  EID (APDU): not available")
    # Also try vendor-specific
    eid_q = get_eid_via_qesim(modem)
    if eid_q:
        print(f"  EID (QESIM): {eid_q}")
    else:
        print("  EID (QESIM): not available")

    # Verify at least one method returned an EID
    if not eid and not eid_q:
        print("\n  WARNING: Could not retrieve EID via any method.")
        print("  The eSIM may not support eUICC, or firmware needs updating.")


def cmd_list(modem: EG21GModemManager) -> None:
    """List installed eSIM profiles."""
    print("\n--- Installed Profiles ---")
    resp = modem.send_command('AT+QESIM="list"', timeout=CMD_TIMEOUT)
    if "ERROR" in resp:
        print("  AT+QESIM=\"list\" not supported or no eSIM present.")
        print(f"  Response: {resp}")
        return

    # Parse profile entries from the response.
    # Expected format: +QESIM: "list",0,<iccid>,<status>,<nickname>,<provider>
    # Multiple profiles may appear as separate +QESIM lines.
    lines = resp.split("\n")
    profiles = []
    for line in lines:
        # Match profile data lines
        match = re.search(
            r'\+QESIM:\s*"list",0'
            r'(?:,(\d{18,20}),(\d+)(?:,"([^"]*)")?(?:,"([^"]*)")?)?',
            line,
        )
        if match and match.group(1):
            profiles.append({
                "iccid": match.group(1),
                "status": match.group(2),
                "nickname": match.group(3) or "",
                "provider": match.group(4) or "",
            })

    if not profiles:
        # Try alternate parsing — some firmware returns all profiles on one line
        iccids = re.findall(r"(\d{18,20})", resp)
        if iccids:
            print(f"  Found {len(iccids)} profile(s) (minimal parsing):")
            for i, iccid in enumerate(iccids, 1):
                print(f"  [{i}] ICCID: {iccid}")
        else:
            print("  No profiles found.")
            print(f"  Raw response: {resp}")
        return

    # Show active ICCID for comparison
    active_iccid = get_iccid(modem)

    for i, p in enumerate(profiles, 1):
        status_label = {
            "0": "disabled",
            "1": "enabled",
        }.get(p["status"], f"unknown({p['status']})")
        active = " <-- active" if active_iccid and p["iccid"] in active_iccid else ""
        print(f"  [{i}] ICCID: {p['iccid']}  Status: {status_label}{active}")
        if p["nickname"]:
            print(f"      Nickname: {p['nickname']}")
        if p["provider"]:
            print(f"      Provider: {p['provider']}")


def cmd_download(modem: EG21GModemManager, activation_code: str) -> None:
    """Download and install an eSIM profile from SM-DP+.

    The activation code is typically obtained from the carrier/MVNO and
    follows the format: LPA:1$<smdp-address>$<matching-id>

    The modem must have network connectivity for the SM-DP+ download to
    succeed (the eUICC communicates with SM-DP+ via BIP over the active
    data bearer).
    """
    print("\n--- Profile Download ---")
    print(f"  Activation code: {activation_code}")

    # Validate activation code format
    if not activation_code.startswith("LPA:") and "$" not in activation_code:
        print("  WARNING: Activation code doesn't match expected LPA format.")
        print("  Expected: LPA:1$<smdp-address>$<matching-id>")
        resp = input("  Continue anyway? [y/N] ")
        if resp.lower() != "y":
            return

    # Ensure BIP authentication is enabled (required for SM-DP+ communication)
    print("  Enabling BIP authentication...")
    bip_resp = modem.send_command('AT+QCFG="bip/auth",1', timeout=CMD_TIMEOUT)
    if "ERROR" in bip_resp:
        print(f"  WARNING: BIP config failed: {bip_resp}")
        print("  Profile download may still work if BIP is already configured.")

    # Check network registration (needed for BIP data path)
    reg_resp = modem.send_command("AT+CEREG?", timeout=CMD_TIMEOUT)
    match = re.search(r"\+CEREG:\s*\d+,(\d+)", reg_resp)
    if not match or int(match.group(1)) not in (1, 5):
        print("  WARNING: Modem is not registered on network.")
        print("  Profile download requires active data connectivity for BIP.")
        resp = input("  Continue anyway? [y/N] ")
        if resp.lower() != "y":
            return

    print("  Starting OTA download (this may take several minutes)...")
    resp = modem.send_command(
        f'AT+QESIM="ota","{activation_code}"',
        timeout=OTA_TIMEOUT,
    )

    if "ERROR" in resp:
        print(f"  ERROR: Download command failed: {resp}")
        return

    # The download is asynchronous — poll for the URC
    print("  Waiting for download completion URC...")
    start = time.time()
    while (time.time() - start) < OTA_TIMEOUT:
        # Read any unsolicited response
        if modem.serial.in_waiting:
            line = modem.serial.readline().decode("utf-8", errors="ignore").strip()
            if "+QESIM:" in line and "ota" in line.lower():
                print(f"  URC: {line}")
                if ",0" in line:
                    print("  Profile download SUCCESSFUL.")
                else:
                    print("  Profile download FAILED."
                          " Check activation code and network.")
                break
        time.sleep(1)
    else:
        print(f"  Timeout after {OTA_TIMEOUT}s waiting for download completion.")
        print("  Check profile list to see if download succeeded.")

    # After profile download, cycle radio to pick up the new profile
    print("  Cycling radio to apply new profile...")
    modem.send_command("AT+CFUN=0", timeout=CMD_TIMEOUT)
    time.sleep(1)
    modem.send_command("AT+CFUN=1", timeout=CMD_TIMEOUT)
    time.sleep(2)

    print("  Done. Run 'list' to see installed profiles.")


def cmd_enable(modem: EG21GModemManager, iccid: str) -> None:
    """Enable (activate) an installed eSIM profile."""
    print("\n--- Enable Profile ---")
    print(f"  ICCID: {iccid}")

    start = time.time()
    resp = modem.send_command(
        f'AT+QESIM="enable","{iccid}"', timeout=PROFILE_OP_TIMEOUT
    )
    elapsed = time.time() - start

    if "ERROR" in resp:
        print(f"  ERROR: {resp}")
        return

    print(f"  Response: {resp}")
    print(f"  Elapsed: {elapsed:.3f}s")

    # Verify the switch
    time.sleep(2)
    new_iccid = get_iccid(modem)
    new_imsi = get_imsi(modem)
    print(f"  Active ICCID: {new_iccid or 'N/A'}")
    print(f"  Active IMSI:  {new_imsi or 'N/A'}")


def cmd_disable(modem: EG21GModemManager, iccid: str) -> None:
    """Disable an installed eSIM profile."""
    print("\n--- Disable Profile ---")
    print(f"  ICCID: {iccid}")

    resp = modem.send_command(
        f'AT+QESIM="disable","{iccid}"', timeout=PROFILE_OP_TIMEOUT
    )
    if "ERROR" in resp:
        print(f"  ERROR: {resp}")
    else:
        print(f"  Response: {resp}")


def cmd_delete(modem: EG21GModemManager, iccid: str) -> None:
    """Delete an installed eSIM profile.

    The profile must be disabled before it can be deleted.
    """
    print("\n--- Delete Profile ---")
    print(f"  ICCID: {iccid}")

    resp = input("  Are you sure you want to delete this profile? [y/N] ")
    if resp.lower() != "y":
        print("  Cancelled.")
        return

    # Ensure profile is disabled first
    print("  Disabling profile before deletion...")
    dis_resp = modem.send_command(
        f'AT+QESIM="disable","{iccid}"', timeout=PROFILE_OP_TIMEOUT
    )
    if "ERROR" in dis_resp and "already" not in dis_resp.lower():
        print(f"  WARNING: Disable failed: {dis_resp}")
        print("  Attempting delete anyway...")

    resp = modem.send_command(
        f'AT+QESIM="delete","{iccid}"', timeout=PROFILE_OP_TIMEOUT
    )
    if "ERROR" in resp:
        print(f"  ERROR: {resp}")
    else:
        print(f"  Response: {resp}")
        print("  Profile deleted.")


def cmd_verify(modem: EG21GModemManager) -> None:
    """Verify that the eSIM is configured for the test framework.

    Checks:
      1. SIM is present and ready
      2. eUICC ID is retrievable
      3. At least one profile is installed
      4. Active profile can register on network
      5. Multiple profiles available (for profile switch tests)
    """
    print("\n--- Test Framework eSIM Verification ---")
    issues = []
    passed = 0

    # Check 1: SIM present
    sim_status = modem.get_sim_status()
    if "READY" in sim_status:
        print("  [PASS] SIM card present and ready")
        passed += 1
    else:
        print(f"  [FAIL] SIM status: {sim_status}")
        issues.append("SIM not ready")

    # Check 2: EID retrievable
    eid = get_eid_via_apdu(modem)
    if not eid:
        eid = get_eid_via_qesim(modem)
    if eid:
        print(f"  [PASS] eUICC ID: {eid}")
        passed += 1
    else:
        print("  [FAIL] Could not retrieve eUICC ID")
        issues.append("EID not retrievable")

    # Check 3: Active profile identifiers
    iccid = get_iccid(modem)
    imsi = get_imsi(modem)
    if iccid and imsi:
        print(f"  [PASS] Active profile: ICCID={iccid}, IMSI={imsi}")
        passed += 1
    else:
        print(f"  [FAIL] Profile identifiers: ICCID={iccid}, IMSI={imsi}")
        issues.append("Could not read profile identifiers")

    # Check 4: Multiple profiles (for profile switch tests)
    resp = modem.send_command('AT+QESIM="list"', timeout=CMD_TIMEOUT)
    iccids = re.findall(r"(\d{18,20})", resp)
    if len(iccids) >= 2:
        print(
            f"  [PASS] {len(iccids)} profiles installed"
            " (profile switch tests will run)"
        )
        passed += 1
    elif len(iccids) == 1:
        print(
            "  [WARN] Only 1 profile installed"
            " (profile switch tests will SKIP)"
        )
        print("         Use 'download <activation-code>' to add more profiles.")
        issues.append("Only 1 profile — need 2+ for switch tests")
    else:
        if "ERROR" in resp:
            print("  [WARN] AT+QESIM not supported — cannot check profile count")
            issues.append("AT+QESIM not available")
        else:
            print("  [FAIL] No profiles detected")
            issues.append("No profiles found")

    # Check 5: Network registration
    reg_resp = modem.send_command("AT+CEREG?", timeout=CMD_TIMEOUT)
    match = re.search(r"\+CEREG:\s*\d+,(\d+)", reg_resp)
    if match and int(match.group(1)) in (1, 5):
        state = "home" if int(match.group(1)) == 1 else "roaming"
        print(f"  [PASS] Network registered ({state})")
        passed += 1
    else:
        stat = match.group(1) if match else "unknown"
        print(f"  [INFO] Not registered on network (CEREG stat={stat})")
        print("         This is expected without a live cell/CMW500.")

    # Summary
    total = passed + len(issues)
    print(f"\n  Result: {passed}/{total} checks passed")
    if issues:
        print("  Issues:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("  eSIM is ready for test framework.")


def main():
    parser = argparse.ArgumentParser(
        description="eSIM setup utility for the NCC2 modem test framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
commands:
  info                 Show modem and eSIM identity information
  list                 List installed eSIM profiles
  download <code>      Download a profile from SM-DP+ using activation code
  enable <iccid>       Enable (activate) an installed profile
  disable <iccid>      Disable an installed profile
  delete <iccid>       Delete an installed profile (disables first)
  verify               Verify eSIM readiness for the test framework
""",
    )
    parser.add_argument(
        "command",
        choices=["info", "list", "download", "enable", "disable", "delete", "verify"],
        help="Operation to perform",
    )
    parser.add_argument(
        "argument",
        nargs="?",
        help="ICCID (for enable/disable/delete) or activation code (for download)",
    )
    parser.add_argument(
        "--port",
        default=None,
        help="Modem serial port (auto-detect if not specified)",
    )

    args = parser.parse_args()

    # Validate argument requirement
    needs_arg = ("download", "enable", "disable", "delete")
    if args.command in needs_arg and not args.argument:
        parser.error(f"'{args.command}' requires an argument")

    modem = connect_modem(args.port)

    try:
        if args.command == "info":
            cmd_info(modem)
        elif args.command == "list":
            cmd_list(modem)
        elif args.command == "download":
            cmd_download(modem, args.argument)
        elif args.command == "enable":
            cmd_enable(modem, args.argument)
        elif args.command == "disable":
            cmd_disable(modem, args.argument)
        elif args.command == "delete":
            cmd_delete(modem, args.argument)
        elif args.command == "verify":
            cmd_verify(modem)
    finally:
        modem.disconnect()


if __name__ == "__main__":
    main()
