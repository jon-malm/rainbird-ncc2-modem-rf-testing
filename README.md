# Rainbird NCC2 Modem Tests

Automated test framework for cellular modem testing using the Rohde & Schwarz CMW500 Base Station Simulator and Quectel EG21-G modem.

## Overview

This framework enables automated testing of cellular connectivity across multiple technologies:

- **LTE** (4G) - Attachment, data connections, signal quality measurements
- **WCDMA/UMTS** (3G) - Voice calls, PS data, BER/BLER measurements
- **GSM/GPRS/EDGE** (2G) - Circuit-switched calls, packet data
- **HSPA** - High-speed data extensions for WCDMA

### Repository Structure

```
mdm_tst_fw/
├── equipment-cmw500/          # CMW500 control library (submodule)
├── modem-manager-eg21/        # Quectel modem control (submodule)
├── tests/
│   ├── conftest.py            # pytest fixtures
│   ├── integration/           # Hardware integration tests
│   ├── end_to_end/            # Internet connectivity tests
│   ├── scenarios/             # Complex test scenarios
│   └── unit/                  # Unit tests (mocked hardware)
└── pyproject.toml
```

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- R&S CMW500 Base Station Simulator with LTE/WCDMA/GSM options
- Quectel EG21-G modem (or compatible)
- Network connection between test host and CMW500

## Installation

1. Clone the repository with submodules:

```bash
git clone --recursive git@gitlab.rainbird.com:repo/firmware/projects/ncc2/mdm_tst_fw.git
cd mdm_tst_fw
```

2. Install dependencies:

```bash
uv sync
```

3. Verify installation:

```bash
uv run pytest tests/ --collect-only
```

---

## Quick Start (Equipment Already Set Up)

If the CMW500 and modem are already connected and configured, you can run tests immediately.

```bash
# Run the full test suite
uv run pytest

# Run integration tests (CMW500 + modem)
uv run pytest tests/integration/

# Run end-to-end tests (requires internet via DAU)
uv run pytest tests/end_to_end/

# Run scenario tests
uv run pytest tests/scenarios/

# Run only LTE tests
uv run pytest -m lte

# Specify a non-default CMW500 IP or modem port
uv run pytest --cmw500-ip=172.22.1.4 --modem-port=/dev/ttyUSB2

# Skip tests that require the modem (CMW500-only tests)
uv run pytest --skip-modem

# Skip end-to-end internet connectivity tests
uv run pytest --skip-end-to-end
```

---

## Equipment Setup Guide

### Required Equipment

| Equipment | Description | Connection |
|-----------|-------------|------------|
| R&S CMW500 | Base Station Simulator | Ethernet (HiSLIP) |
| Quectel EG21-G | LTE Cat 1 Modem | USB to test host |
| RF Cable | Coaxial cable (attenuator optional) | CMW500 RF COM1 to modem antenna port |
| SIM Card | Test SIM (optional) | Modem SIM slot |

### Network Diagram

```
┌─────────────────┐          ┌─────────────────┐
│   Test Host     │          │    CMW500       │
│   (Python)      │          │                 │
│                 │          │  ┌───────────┐  │
│  pytest         │◄─────────┤  │ REMOTE    │  │  Ethernet (HiSLIP/SCPI)
│  equipment-     │  LAN     │  │ LAN       │  │  CMW500: 172.22.1.4/16
│  cmw500         │          │  └───────────┘  │
│                 │          │                 │
│  modem-manager- │          │  ┌───────────┐  │
│  eg21           │          │  │ LAN DAU   │  │  Ethernet (Data traffic)
│                 │          │  │           │──┼──► Internet/AWS
│                 │          │  └───────────┘  │
└────────┬────────┘          │                 │
         │ USB               │  ┌───────────┐  │
         │                   │  │ RF COM1   │  │
         ▼                   │  └─────┬─────┘  │
┌─────────────────┐          └────────┼────────┘
│  Quectel EG21   │                   │
│  Modem          │◄──────────────────┘
│                 │     RF Cable (coax, attenuator optional)
└─────────────────┘
```

### Step 1: CMW500 Network Configuration

The CMW500 has two Ethernet interfaces:

#### REMOTE LAN (Control Interface)
- Purpose: SCPI/HiSLIP commands from test host
- CMW500 IP: `172.22.1.4/16` (static)
- Test Host IP: `172.22.0.100/16` (static, on connected NIC)
- Connect directly to test host or via switch

Configure CMW500 via front panel:
1. Press **Setup** > **Remote** > **Network**
2. Set IP Address: `172.22.1.4`
3. Set Subnet Mask: `255.255.0.0`

Configure Test Host (Linux example):
```bash
# Set static IP on the NIC connected to CMW500 REMOTE LAN
sudo ip addr add 172.22.0.100/16 dev eth0
sudo ip link set eth0 up

# Verify connectivity
ping 172.22.1.4
```

#### LAN DAU (Data Application Unit)
- Purpose: Routes UE data traffic to external network
- Default Mode: DHCP (recommended)
- Connect to network with internet access

Configure via CMW500 front panel:
1. Press **Setup** > **DAU** > **LAN**
2. Set Mode: **DHCP** (or static if required)

### Step 2: RF Connection

Connect CMW500 RF COM1 to the modem antenna connector using a coaxial cable.

**Attenuation (Optional):** The CMW500 RF1 COM port can accept up to 2W input power, which matches the maximum output of the Quectel EG21-G (~2W). Direct connection without an attenuator is acceptable for this setup.

If you choose to use an external attenuator:
- Configure the external attenuation value in the CMW500 so RF measurements remain accurate
- Via front panel: **Setup** > **RF Connector** > **External Attenuation**
- Or via SCPI: configure the external attenuation offset for the connector in use

**Power level guidance:**
- CMW500 output power: configurable (-20 to -120 dBm at antenna connector)
- Start with low power (-80 dBm) and increase gradually
- Typical test level: -60 to -80 dBm at modem

### Step 3: Modem Connection

1. Connect Quectel EG21-G via USB to test host
2. Verify serial ports appear:

```bash
ls /dev/ttyUSB*
# Expected: /dev/ttyUSB0, /dev/ttyUSB1, /dev/ttyUSB2, /dev/ttyUSB3
```

3. Identify AT command port (typically `/dev/ttyUSB2` or `/dev/ttyUSB3`):

```bash
# Test AT command response
echo -e "AT\r" > /dev/ttyUSB2 && cat /dev/ttyUSB2
# Should respond: OK
```

4. (Optional) Insert test SIM card if using SIM-based authentication

### Step 4: Verify CMW500 Connectivity

Test HiSLIP connection from test host.

#### VISA Backend Requirement

The `RsInstrument` library requires a VISA backend. You have two options:

**Option A: R&S VISA (recommended)**

Download and install R&S VISA from:
https://www.rohde-schwarz.com/us/applications/r-s-visa-application-note_56280-148812.html

After installation, connect without any special options:

```bash
uv run python -c "
from RsInstrument import RsInstrument
instr = RsInstrument('TCPIP::172.22.1.4::hislip0::INSTR')
print(instr.idn_string)
instr.close()
"
```

**Option B: pyvisa-py (pure Python, no external install)**

Use the pure Python VISA implementation with socket I/O if you prefer not to install R&S VISA:

```bash
uv run python -c "
from RsInstrument import RsInstrument
instr = RsInstrument('TCPIP::172.22.1.4::hislip0::INSTR', options='SelectVisa=SocketIo')
print(instr.idn_string)
instr.close()
"
```

Expected output:
```
Rohde&Schwarz,CMW500,1234567890,3.8.10.xx
```

### Step 5: Environment Configuration

Create a `.env` file or set environment variables:

```bash
# CMW500 connection
export CMW500_IP=172.22.1.4
export CMW500_RESOURCE="TCPIP::172.22.1.4::hislip0::INSTR"

# Modem
export MODEM_PORT=/dev/ttyUSB2

# End-to-end testing (optional)
export CMW500_TEST_ENDPOINT=your-aws-test-server.com
```

Or use a YAML configuration file:

```yaml
# config/cmw500.yaml
connection:
  resource_name: "TCPIP::172.22.1.4::hislip0::INSTR"
  timeout_ms: 10000

lte:
  band: 7
  bandwidth_mhz: 10
  dl_earfcn: 3100
  dl_power_dbm: -60.0

dau:
  lan_dau_mode: dhcp
  nat_enabled: true
```

---

## Running Tests

### Basic Commands

```bash
# Run all tests (skips hardware tests by default in CI)
uv run pytest tests/

# Run with hardware
uv run pytest tests/ --cmw500-ip=172.22.1.4

# Skip hardware tests
uv run pytest tests/ --skip-modem

# Skip end-to-end internet tests
uv run pytest tests/ --skip-end-to-end

# Run specific technology
uv run pytest tests/ -m lte
uv run pytest tests/ -m wcdma
uv run pytest tests/ -m gsm

# Run specific test file
uv run pytest tests/integration/test_lte_attach.py -v
```

### Test Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.hardware` | Requires CMW500 and/or modem |
| `@pytest.mark.lte` | LTE-specific tests |
| `@pytest.mark.wcdma` | WCDMA/UMTS tests |
| `@pytest.mark.gsm` | GSM/GPRS/EDGE tests |
| `@pytest.mark.end_to_end` | Requires internet via DAU |
| `@pytest.mark.slow` | Tests taking >30 seconds |

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--cmw500-ip` | CMW500 IP address | `192.168.1.100` |
| `--cmw500-config` | Path to YAML config file | None |
| `--modem-port` | Modem serial port | Auto-detect |
| `--skip-modem` | Skip hardware tests | False |
| `--skip-end-to-end` | Skip end-to-end tests | False |
| `--aws-endpoint` | AWS test server URL | None |

### Example Test Session

```bash
# 1. Verify equipment connectivity
uv run pytest tests/integration/test_cmw500_connection.py -v

# 2. Run LTE attachment tests
uv run pytest tests/integration/test_lte_attach.py -v --cmw500-ip=172.22.1.4

# 3. Run full integration suite
uv run pytest tests/integration/ -v --cmw500-ip=172.22.1.4

# 4. Run end-to-end with AWS endpoint
uv run pytest tests/end_to_end/ -v \
    --cmw500-ip=172.22.1.4 \
    --aws-endpoint=test.example.com
```

---

## Test Categories

### Integration Tests (`tests/integration/`)

Tests requiring CMW500 and modem hardware:

- `test_cmw500_connection.py` - CMW500 connectivity and system info
- `test_lte_attach.py` - LTE cell configuration and UE attachment
- `test_signal_quality.py` - RF signal measurements
- `test_data_throughput.py` - Data connection and throughput
- `test_mode_fallback.py` - Technology fallback scenarios

### End-to-End Tests (`tests/end_to_end/`)

Tests requiring full data path through CMW500 DAU to internet:

- `test_aws_connectivity.py` - Ping and HTTP to AWS test server
- `test_dns_resolution.py` - DNS resolution through DAU
- `test_data_transfer.py` - Upload/download through full path

### Scenarios (`tests/scenarios/`)

Complex multi-step test scenarios:

- Carrier fallback testing
- QoS degradation scenarios
- Handover testing (future)

---

## Troubleshooting

### CMW500 Connection Issues

**Problem:** `LibraryError: Error while accessing rsvisa` or `cannot open shared object file`

This error means no VISA backend is installed. Solutions:
1. Install R&S VISA from https://www.rohde-schwarz.com/us/applications/r-s-visa-application-note_56280-148812.html
2. Or use pyvisa-py with socket I/O by adding `options='SelectVisa=SocketIo'` to `RsInstrument()` calls

See [Step 4: Verify CMW500 Connectivity](#step-4-verify-cmw500-connectivity) for details.

**Problem:** `CMW500ConnectionError: Failed to connect`

1. Verify IP address: `ping 172.22.1.4`
2. Check HiSLIP port: `nc -zv 172.22.1.4 4880`
3. Verify no other application has connection open
4. Check CMW500 remote settings allow LAN connections

**Problem:** `Connected instrument is not a CMW500`

- Verify correct VISA resource string
- Check instrument is a CMW500 (not CMW100, etc.)

### Modem Issues

**Problem:** Modem not detected

1. Check USB connection: `lsusb | grep Quectel`
2. Verify serial ports: `ls /dev/ttyUSB*`
3. Check permissions: `sudo usermod -a -G dialout $USER`
4. Reload udev rules if needed

**Problem:** UE registration timeout

1. Verify RF connection and power levels
2. Check CMW500 cell is activated
3. Verify band/EARFCN supported by modem
4. Check modem AT+COPS? for network search status

### RF Issues

**Problem:** No signal / weak signal

1. Check RF cable connections
2. Verify attenuator values
3. Increase CMW500 output power (carefully)
4. Check antenna connector on modem

**Problem:** Signal too strong (distortion)

1. Add more attenuation
2. Reduce CMW500 output power
3. Typical test level: -60 to -80 dBm at modem

### DAU / Internet Issues

**Problem:** No internet through DAU

1. Verify LAN DAU has IP (DHCP or static)
2. Check NAT is enabled on CMW500
3. Verify DNS servers configured
4. Test DAU ping: use `dau.ping_external("8.8.8.8")`

---

## Configuration Reference

### LTE Bands (Quectel EG21-G)

| Band | Frequency | Default EARFCN | Notes |
|------|-----------|----------------|-------|
| B1 | 2100 MHz | 300 | |
| B3 | 1800 MHz | 1575 | |
| B7 | 2600 MHz | 3100 | Default |
| B8 | 900 MHz | 3625 | |
| B20 | 800 MHz | 6300 | |

### Default Test Configuration

```python
LTECellConfig(
    band=LTEBand.BAND_7,
    bandwidth=LTEBandwidth.BW_10_MHZ,
    dl_earfcn=3100,
    dl_power_dbm=-60.0,
    mcc="001",  # Test network
    mnc="01",
)
```

---

## Development

### Running Linter

```bash
uv run ruff check .
uv run ruff format .
```

### Adding New Tests

1. Create test file in appropriate directory
2. Use fixtures from `conftest.py`
3. Add appropriate markers (`@pytest.mark.hardware`, etc.)
4. Follow existing test patterns

### Contributing

1. Create feature branch
2. Make changes with tests
3. Run full test suite
4. Submit pull request

---

## License

Proprietary. Internal use only.
