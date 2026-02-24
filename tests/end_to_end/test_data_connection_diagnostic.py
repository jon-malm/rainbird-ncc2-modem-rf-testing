"""
Data connection diagnostic test.

Steps through the full data-path setup with verbose logging at each stage
so we can pinpoint exactly where the connection breaks down:

1. Configure the CMW500 and modem like we are going to issue pings
2. Check that a network interface appears for the modem on the host PC
3. Check the modem status for anything relevant to the data connection
4. Check the CMW500 DAU has a connection to the internet
"""

import logging
import re
import subprocess
import time

import pytest

from tests.constants import (
    AT_CMD_TIMEOUT,
    AT_PDP_ACTIVATE_TIMEOUT,
    AT_PDP_DEACTIVATE_TIMEOUT,
    CMW_UE_REGISTRATION_TIMEOUT_SEC,
    POLL_INTERVAL_SEC,
    RADIO_OFF_SETTLE_SEC,
    RECOVERY_TIMEOUT_SEC,
    SIGNAL_SETTLE_SEC,
    TEST_TIMEOUT_EXTENDED,
)

logger = logging.getLogger(__name__)


def _log_section(title: str) -> None:
    """Print a visible section header in the test log."""
    border = "=" * 60
    logger.info("")
    logger.info(border)
    logger.info("  %s", title)
    logger.info(border)


def _log_kv(key: str, value: str) -> None:
    """Log a key-value diagnostic line."""
    logger.info("  %-30s : %s", key, value)


@pytest.mark.hardware
@pytest.mark.lte
@pytest.mark.end_to_end
@pytest.mark.timeout(TEST_TIMEOUT_EXTENDED)
class TestDataConnectionDiagnostic:
    """Step-by-step data connection diagnostic with verbose logging."""

    def test_data_connection_diagnostic(
        self,
        end_to_end_data_path,
        modem,
        aws_test_endpoint,
    ):
        """Walk through every stage of the data path, logging diagnostics."""
        cell = end_to_end_data_path["cell"]
        dau = end_to_end_data_path["dau"]
        sign = "SIGN1"

        # ==================================================================
        # STAGE 1 — Verify cell and DAU are up (handled by fixtures)
        # ==================================================================
        _log_section("STAGE 1: LTE cell and DAU status")

        cell_state = cell.query_cmd_safe(f"SOURce:LTE:{sign}:CELL:STATe?")
        _log_kv("Cell state", str(cell_state).strip())

        rrc_state = cell.query_cmd_safe(f"SENSe:LTE:{sign}:RRCState?")
        _log_kv("RRC state (pre-registration)", str(rrc_state).strip())

        lan_info = dau.get_lan_dau_info()
        _log_kv("LAN DAU mode", lan_info.mode)
        _log_kv("LAN DAU IP", lan_info.ip_address)
        _log_kv("LAN DAU netmask", lan_info.netmask)
        _log_kv("LAN DAU gateway", lan_info.gateway)

        nat_status = dau.get_nat_status()
        _log_kv("NAT enabled", str(nat_status.enabled))

        dns = dau.get_dns_servers()
        _log_kv("DNS primary", dns.primary)
        _log_kv("DNS secondary", dns.secondary)

        logger.info("  Cell + DAU configured by fixtures OK")

        # ==================================================================
        # STAGE 2 — Register modem on LTE cell
        # ==================================================================
        _log_section("STAGE 2: Register modem on LTE cell")

        # Show modem's initial state
        cereg = modem.send_command("AT+CEREG?")
        _log_kv("CEREG (initial)", cereg.strip())

        cfun = modem.send_command("AT+CFUN?")
        _log_kv("CFUN (initial)", cfun.strip())

        # Cycle radio to trigger fresh search.  Allow extra settle time
        # after CFUN=1 — if previous tests left the modem in a stressed
        # state (e.g. post-RAT-switch or detach), the baseband needs
        # additional time before it begins scanning for the LTE cell.
        logger.info("  Cycling radio (CFUN=0 -> CFUN=1) ...")
        modem.send_command("AT+CFUN=0", timeout=AT_CMD_TIMEOUT)
        time.sleep(RADIO_OFF_SETTLE_SEC)
        modem.send_command("AT+CFUN=1", timeout=AT_CMD_TIMEOUT)
        time.sleep(SIGNAL_SETTLE_SEC)

        # Poll for registration — use the recovery timeout (90s) rather than
        # the standard timeout (60s) because this diagnostic test may run
        # after tests that left the modem in a stressed state
        registered = False
        start = time.time()
        while (time.time() - start) < RECOVERY_TIMEOUT_SEC:
            resp = modem.send_command("AT+CEREG?")
            match = re.search(r"\+CEREG:\s*\d+,(\d+)", resp)
            if match:
                stat = int(match.group(1))
                if stat in (1, 5):
                    elapsed = time.time() - start
                    _log_kv("CEREG stat", str(stat))
                    _log_kv("Registration time", f"{elapsed:.1f}s")
                    registered = True
                    break
            time.sleep(POLL_INTERVAL_SEC)

        if not registered:
            _log_kv("CEREG (final)", modem.send_command("AT+CEREG?").strip())
            pytest.fail("Modem failed to register within timeout")

        # Verify CMW500 side
        ue_registered = cell.wait_for_ue_registration(
            timeout_sec=CMW_UE_REGISTRATION_TIMEOUT_SEC
        )
        _log_kv("CMW500 sees UE registered", str(ue_registered))

        rrc_state = cell.query_cmd_safe(f"SENSe:LTE:{sign}:RRCState?")
        _log_kv("RRC state", str(rrc_state).strip())

        ue_info = cell.get_ue_info()
        _log_kv("UE IMSI", str(ue_info.imsi))
        _log_kv("UE IMEI", str(ue_info.imei))
        _log_kv("UE state", str(ue_info.state))

        time.sleep(SIGNAL_SETTLE_SEC)

        # ==================================================================
        # STAGE 3 — Activate PDP context (data bearer)
        # ==================================================================
        _log_section("STAGE 3: Activate PDP context from modem side")

        # Check current PDP context list
        cgdcont = modem.send_command("AT+CGDCONT?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CGDCONT (defined)", cgdcont.strip().replace("\n", " | "))

        cgact = modem.send_command("AT+CGACT?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CGACT (before)", cgact.strip().replace("\n", " | "))

        # Configure PDP context 1 with APN "test"
        logger.info('  Setting PDP context: AT+CGDCONT=1,"IP","test"')
        cgdcont_resp = modem.send_command(
            'AT+CGDCONT=1,"IP","test"', timeout=AT_CMD_TIMEOUT
        )
        _log_kv("CGDCONT=1 response", cgdcont_resp.strip())

        # Verify the definition took effect
        cgdcont_check = modem.send_command("AT+CGDCONT?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CGDCONT (after define)", cgdcont_check.strip().replace("\n", " | "))

        cid1_defined = "+CGDCONT: 1," in cgdcont_check
        _log_kv("CID 1 now defined", str(cid1_defined))

        # Deactivate first if already active (clean slate)
        if "+CGACT: 1,1" in cgact:
            logger.info("  PDP context already active - deactivating first")
            modem.send_command("AT+CGACT=0,1", timeout=AT_PDP_DEACTIVATE_TIMEOUT)
            time.sleep(RADIO_OFF_SETTLE_SEC)

        # Query CMW500 DAU address mode (this works on B450 DAU)
        dau_addr_type = cell.query_cmd_safe(
            "CONFigure:DATA:CONTrol:IPVFour:ADDRess:TYPE?"
        )
        _log_kv("CMW500 DAU addr type", str(dau_addr_type).strip())

        # Query DNS configuration
        dns_primary_type = cell.query_cmd_safe(
            "CONFigure:DATA:CONTrol:DNS:PRIMary:STYPe?"
        )
        _log_kv("CMW500 DNS primary type", str(dns_primary_type).strip())

        # Activate PDP context
        logger.info("  Activating PDP: AT+CGACT=1,1")
        pdp_resp = modem.send_command("AT+CGACT=1,1", timeout=AT_PDP_ACTIVATE_TIMEOUT)
        _log_kv("CGACT=1,1 response", pdp_resp.strip())

        pdp_ok = "OK" in pdp_resp and "ERROR" not in pdp_resp
        if not pdp_ok:
            # Try Quectel-specific data call activation
            logger.info("  CGACT failed, trying Quectel QIACT approach...")
            # Configure Quectel PDP context
            modem.send_command('AT+QICSGP=1,1,"test","","",1', timeout=AT_CMD_TIMEOUT)
            qiact_resp = modem.send_command(
                "AT+QIACT=1", timeout=AT_PDP_ACTIVATE_TIMEOUT
            )
            _log_kv("QIACT=1 response", qiact_resp.strip())

            # Check Quectel data call status
            qiact_check = modem.send_command("AT+QIACT?", timeout=AT_CMD_TIMEOUT)
            _log_kv("QIACT? (after)", qiact_check.strip().replace("\n", " | "))

        cgact_after = modem.send_command("AT+CGACT?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CGACT (after)", cgact_after.strip().replace("\n", " | "))

        pdp_active = "+CGACT: 1,1" in cgact_after
        _log_kv("PDP context 1 active", str(pdp_active))

        # Query assigned IP address
        cgpaddr_raw = modem.send_command("AT+CGPADDR=1", timeout=AT_CMD_TIMEOUT)
        # Parse IP from response like '+CGPADDR: 1,"10.0.0.1"'
        ip_match = re.search(r'\+CGPADDR:\s*\d+,"([^"]*)"', cgpaddr_raw)
        modem_ip = ip_match.group(1) if ip_match else ""
        if not modem_ip or modem_ip == "0.0.0.0":
            # Try all CIDs
            cgpaddr_all_pdp = modem.send_command("AT+CGPADDR", timeout=AT_CMD_TIMEOUT)
            _log_kv("CGPADDR (all CIDs)", cgpaddr_all_pdp.strip().replace("\n", " | "))
            # Also try Quectel data call
            qiact_ip = modem.send_command("AT+QIACT?", timeout=AT_CMD_TIMEOUT)
            _log_kv("QIACT? (IP check)", qiact_ip.strip().replace("\n", " | "))
        _log_kv("CGPADDR (modem IP)", modem_ip or "(none)")

        # Check RRC state after PDP activation
        rrc_after = cell.query_cmd_safe(f"SENSe:LTE:{sign}:RRCState?")
        _log_kv("RRC state (after PDP)", str(rrc_after).strip())

        # ==================================================================
        # STAGE 4 — Check host network interface for modem
        # ==================================================================
        _log_section("STAGE 4: Check host PC network interface for modem")

        # Quectel EG21-G typically exposes a USB ECM/RNDIS/QMI interface.
        # Common names: usb0, wwan0, enx<mac>, or eth<N>.
        # Also check if the modem's QMI/MBIM data mode is enabled.

        # Query modem USB net mode
        usbnetmode = modem.send_command('AT+QCFG="usbnet"', timeout=AT_CMD_TIMEOUT)
        _log_kv("QCFG usbnet", usbnetmode.strip())

        # List host network interfaces
        try:
            ip_link = subprocess.run(
                ["ip", "-br", "link"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            logger.info("  Host interfaces (ip -br link):")
            for line in ip_link.stdout.strip().splitlines():
                logger.info("    %s", line)
        except Exception as e:
            _log_kv("ip link", f"error: {e}")

        # Check for modem-related interfaces with IP addresses
        modem_iface = None
        try:
            ip_addr = subprocess.run(
                ["ip", "-br", "addr"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            logger.info("  Host interfaces with IPs (ip -br addr):")
            for line in ip_addr.stdout.strip().splitlines():
                logger.info("    %s", line)
                # Look for typical modem interface patterns
                lower = line.lower()
                if any(
                    pattern in lower
                    for pattern in ("usb", "wwan", "wwp", "qmi", "mbim", "cdc")
                ):
                    modem_iface = line.split()[0]
                    _log_kv("Candidate modem interface", modem_iface)
        except Exception as e:
            _log_kv("ip addr", f"error: {e}")

        # Also try listing USB network devices via /sys
        try:
            usb_net = subprocess.run(
                ["ls", "-la", "/sys/class/net/"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            logger.info("  /sys/class/net/ entries:")
            for line in usb_net.stdout.strip().splitlines():
                if "usb" in line.lower():
                    logger.info("    %s", line)
        except Exception as e:
            _log_kv("/sys/class/net", f"error: {e}")

        if modem_iface:
            logger.info("  Found modem interface: %s", modem_iface)
            # Try to get detailed info
            try:
                detail = subprocess.run(
                    ["ip", "addr", "show", modem_iface],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                logger.info("  Interface detail:")
                for line in detail.stdout.strip().splitlines():
                    logger.info("    %s", line)
            except Exception as e:
                _log_kv("Interface detail", f"error: {e}")
        else:
            logger.warning("  No modem network interface found on host")
            logger.info(
                '  The modem may need AT+QCFG="usbnet",1 (ECM) or '
                'AT+QCFG="usbnet",0 (NDIS/QMI) to expose a network interface'
            )

        # ==================================================================
        # STAGE 5 — Modem data connection diagnostics
        # ==================================================================
        _log_section("STAGE 5: Modem data connection status")

        # Registration detail (extended CEREG with LAC/CI)
        modem.send_command("AT+CEREG=2", timeout=AT_CMD_TIMEOUT)
        cereg_detail = modem.send_command("AT+CEREG?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CEREG (verbose)", cereg_detail.strip())
        # Restore normal CEREG URC mode
        modem.send_command("AT+CEREG=0", timeout=AT_CMD_TIMEOUT)

        # Operator info
        cops = modem.send_command("AT+COPS?", timeout=AT_CMD_TIMEOUT)
        _log_kv("COPS (operator)", cops.strip())

        # Serving cell info (Quectel-specific)
        qeng = modem.send_command('AT+QENG="servingcell"', timeout=AT_CMD_TIMEOUT)
        _log_kv("QENG servingcell", qeng.strip())

        # Signal quality
        csq = modem.send_command("AT+CSQ", timeout=AT_CMD_TIMEOUT)
        _log_kv("CSQ (signal)", csq.strip())

        # Quectel signal info
        qcsq = modem.send_command("AT+QCSQ", timeout=AT_CMD_TIMEOUT)
        _log_kv("QCSQ (LTE detail)", qcsq.strip())

        # Network registration status on CS side
        creg = modem.send_command("AT+CREG?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CREG (CS reg)", creg.strip())

        # Packet domain attach state
        cgatt = modem.send_command("AT+CGATT?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CGATT (PS attach)", cgatt.strip())

        # All PDP context addresses
        cgpaddr_all = modem.send_command("AT+CGPADDR", timeout=AT_CMD_TIMEOUT)
        _log_kv("CGPADDR (all CIDs)", cgpaddr_all.strip().replace("\n", " | "))

        # Quectel data call status
        qiact = modem.send_command("AT+QIACT?", timeout=AT_CMD_TIMEOUT)
        _log_kv("QIACT (data call)", qiact.strip().replace("\n", " | "))

        # APN used
        cgdcont_final = modem.send_command("AT+CGDCONT?", timeout=AT_CMD_TIMEOUT)
        _log_kv("CGDCONT (final)", cgdcont_final.strip().replace("\n", " | "))

        # ==================================================================
        # STAGE 6 — CMW500 DAU internet connectivity
        # ==================================================================
        _log_section("STAGE 6: CMW500 DAU internet connectivity check")

        # Ping the default test endpoint from DAU
        # Wrapped in try/except because a VISA connection loss during ping
        # should not prevent us from seeing the diagnostic summary.
        target = aws_test_endpoint or "3.151.226.42"
        _log_kv("Ping target", target)

        dau_reachable = None  # None = could not test, True/False = result
        try:
            result = dau.ping_external(target, count=4, timeout=5.0)
            dau_reachable = result.success
            _log_kv("Ping success", str(result.success))
            _log_kv("Packets sent", str(result.packets_sent))
            _log_kv("Packets received", str(result.packets_received))
            if result.success:
                _log_kv("RTT avg (ms)", f"{result.rtt_avg_ms:.1f}")

            if not result.success:
                logger.warning(
                    "  DAU cannot reach %s - check LAN DAU cable and network",
                    target,
                )
                # Also try pinging the DAU gateway
                if lan_info.gateway and lan_info.gateway not in ("", "0.0.0.0"):
                    logger.info("  Trying to ping gateway %s ...", lan_info.gateway)
                    try:
                        gw_result = dau.ping_external(
                            lan_info.gateway, count=2, timeout=3.0
                        )
                        _log_kv("Gateway ping", str(gw_result.success))
                    except Exception as e:
                        _log_kv("Gateway ping", f"error: {e}")

                # Try pinging a well-known DNS server
                logger.info("  Trying to ping 8.8.8.8 ...")
                try:
                    dns_result = dau.ping_external("8.8.8.8", count=2, timeout=3.0)
                    _log_kv("8.8.8.8 ping", str(dns_result.success))
                except Exception as e:
                    _log_kv("8.8.8.8 ping", f"error: {e}")
        except Exception as e:
            dau_reachable = None
            logger.error("  DAU ping failed with VISA/SCPI error: %s", e)
            logger.error("  This usually means the CMW500 VISA connection was lost.")

        # ==================================================================
        # SUMMARY
        # ==================================================================
        _log_section("DIAGNOSTIC SUMMARY")
        _log_kv("LTE cell", str(cell_state).strip())
        _log_kv("Modem registered", str(registered))
        _log_kv("PDP context active", str(pdp_active))
        _log_kv("Modem IP", modem_ip or "(none)")
        _log_kv("Host modem interface", modem_iface or "NOT FOUND")
        _log_kv("LAN DAU mode", lan_info.mode)
        _log_kv("LAN DAU IP", lan_info.ip_address)
        if dau_reachable is None:
            _log_kv("DAU can reach internet", "UNKNOWN (VISA error)")
        else:
            _log_kv("DAU can reach internet", str(dau_reachable))
