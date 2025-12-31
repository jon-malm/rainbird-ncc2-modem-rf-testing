# CMW500 Test Framework

A comprehensive Python test framework for network simulation and RF testing on the Rohde & Schwarz CMW500 Wideband Radio Communication Tester.

## Features

- **LTE Signaling Control**: Configure and control LTE cells, manage UE connections, perform RF measurements
- **WCDMA/UMTS Signaling**: 3G cell configuration, voice calls, data connections, BER/BLER measurements
- **GSM/GPRS/EDGE Signaling**: 2G/2.5G/2.75G cell control, voice, packet data, frequency hopping
- **HSPA Support**: HSDPA/HSUPA high-speed data, DC-HSDPA, MIMO configuration
- **Network Simulation**: Fading channel simulation, path loss modeling, mobility scenarios
- **General Purpose RF**: Signal generation, power measurements, spectrum analysis
- **Configuration Management**: YAML config files, command-line interface, environment variables
- **Extensible Architecture**: Modular design for easy extension to 5G NR and other technologies

## Requirements

- Python 3.8+
- Network access to CMW500 instrument
- Optional: PyYAML for config file support

## Installation

### From Source

```bash
cd cmw500_test_framework
pip install -e .

# With YAML support
pip install -e ".[yaml]"

# With development tools
pip install -e ".[dev]"
```

### Dependencies Only

```bash
pip install pyyaml  # Optional, for config file support
```

## Quick Start

### Basic Connection

```python
from cmw500_test_framework import CMW500Client

# Connect to CMW500
with CMW500Client("192.168.1.100") as client:
    # Get instrument information
    info = client.get_system_info()
    print(f"Connected to: {info.model} (S/N: {info.serial_number})")
```

### LTE Cell Configuration

```python
from cmw500_test_framework import CMW500Client

with CMW500Client("192.168.1.100") as client:
    # Configure LTE cell
    client.lte.configure_cell(
        band=1,
        bandwidth_mhz=10,
        duplex_mode="FDD",
    )

    # Set downlink power
    client.lte.set_dl_power(rs_epre_dbm=-85)

    # Turn on cell
    client.lte.cell_on()

    # Wait for UE to attach
    client.lte.wait_for_attach(timeout=60)

    # Perform measurements
    tx_power = client.lte.measure_tx_power()
    print(f"PUSCH Power: {tx_power.pusch_power_dbm} dBm")

    # Turn off cell
    client.lte.cell_off()
```

### WCDMA/UMTS Cell Configuration

```python
from cmw500_test_framework import CMW500Client

with CMW500Client("192.168.1.100") as client:
    # Configure WCDMA cell
    client.wcdma.configure_cell(
        band=1,
        uarfcn_dl=10700,
        scrambling_code=0,
    )

    # Set downlink power
    client.wcdma.set_dl_power(cpich_power_dbm=-60)

    # Turn on cell and wait for attach
    client.wcdma.cell_on()
    client.wcdma.wait_for_attach(timeout=60)

    # Configure and start HSPA
    client.hspa.configure_hsdpa(category=10, modulation="Q16")
    client.hspa.configure_hsupa(category=6)
    client.hspa.start_hsdpa()
    client.hspa.start_hsupa()

    # Measure throughput
    result = client.hspa.measure_throughput()
    print(f"HSDPA: {result.hsdpa_throughput_kbps} kbps")
    print(f"HSUPA: {result.hsupa_throughput_kbps} kbps")

    client.wcdma.cell_off()
```

### GSM/GPRS Cell Configuration

```python
from cmw500_test_framework import CMW500Client

with CMW500Client("192.168.1.100") as client:
    # Configure GSM cell
    client.gsm.configure_cell(
        band="GSM900",
        arfcn=50,
        bsic=1,
    )

    # Set downlink power
    client.gsm.set_dl_power(bcch_level_dbm=-60)

    # Turn on cell
    client.gsm.cell_on()
    client.gsm.wait_for_attach(timeout=60)

    # Setup voice call
    client.gsm.setup_voice_call(codec="FR")

    # Or configure GPRS/EDGE for data
    client.gsm.configure_gprs(multislot_class=12, coding_scheme="CS4")
    client.gsm.attach_gprs(apn="test")

    # Measure TX power
    tx_power = client.gsm.measure_tx_power()
    print(f"Burst Power: {tx_power.burst_power_dbm} dBm")

    client.gsm.cell_off()
```

### Network Simulation with Fading

```python
from cmw500_test_framework import CMW500Client
from cmw500_test_framework.applications.network_simulation import NetworkSimulator

with CMW500Client("192.168.1.100") as client:
    sim = NetworkSimulator(client)

    # Configure fading channel
    sim.configure_fading(
        profile="EVA70",      # Extended Vehicular A, 70 Hz Doppler
        correlation="LOW",    # Low MIMO correlation
    )

    # Enable fading
    sim.enable_fading()

    # Or use predefined scenarios
    scenario = NetworkSimulator.scenario_vehicular()
    sim.load_scenario(scenario)
```

### Using Configuration Files

Create `cmw500_config.yaml`:

```yaml
instrument:
  host: "192.168.1.100"
  port: 5025
  timeout: 10.0

lte:
  band: 1
  bandwidth_mhz: 10.0
  rs_epre_dbm: -85.0

fading:
  enabled: true
  profile: "EPA5"
  correlation: "LOW"
```

Use in Python:

```python
from cmw500_test_framework import CMW500Client
from cmw500_test_framework.core.config import Config

config = Config.from_file("cmw500_config.yaml")
client = CMW500Client.from_config(config)
```

## Command-Line Interface

The framework includes a comprehensive CLI:

```bash
# Show instrument information
cmw500-cli info 192.168.1.100

# Send SCPI query
cmw500-cli query 192.168.1.100 "*IDN?"

# Control LTE cell
cmw500-cli lte-cell 192.168.1.100 --on --band 1 --bandwidth 10
cmw500-cli lte-cell 192.168.1.100 --off

# Perform measurements
cmw500-cli measure 192.168.1.100 power -f 1950
cmw500-cli measure 192.168.1.100 tx
cmw500-cli measure 192.168.1.100 aclr

# Generate RF signal
cmw500-cli generate 192.168.1.100 -f 1950 --power -30
cmw500-cli generate 192.168.1.100 --off

# Load network scenario
cmw500-cli scenario 192.168.1.100 vehicular --enable-fading

# Run test from config file
cmw500-cli run-test config.yaml --start-cell --wait-attach

# Generate sample config
cmw500-cli config-gen --host 192.168.1.100 -o my_config.yaml
```

## Module Reference

### Core Modules

| Module | Description |
|--------|-------------|
| `core.client` | High-level CMW500Client interface |
| `core.scpi` | Low-level SCPI communication |
| `core.config` | Configuration management |

### Application Modules

| Module | Description |
|--------|-------------|
| `applications.lte` | LTE signaling and measurements |
| `applications.wcdma` | WCDMA/UMTS signaling and measurements |
| `applications.gsm` | GSM/GPRS/EDGE signaling and measurements |
| `applications.hspa` | HSDPA/HSUPA high-speed packet access |
| `applications.gprf` | General purpose RF generator/analyzer |
| `applications.network_simulation` | Network simulation and fading |

### Utility Modules

| Module | Description |
|--------|-------------|
| `utils.helpers` | Frequency/power formatting, path loss calculations |
| `utils.logging_config` | Logging configuration |

## SCPI Command Reference

The framework abstracts SCPI commands, but you can also send raw commands:

```python
# Send raw SCPI command
client.send_command("CONFigure:LTE:SIGN:CELL:BANDwidth:DL B100")

# Query raw SCPI
response = client.query("CONFigure:LTE:SIGN:CELL:BANDwidth:DL?")
print(response.value)
```

### Common SCPI Subsystems

| Subsystem | Description |
|-----------|-------------|
| `CONFigure:LTE:SIGN:...` | LTE signaling configuration |
| `SOURce:LTE:SIGN:...` | LTE signal source control |
| `MEASure:LTE:SIGN:...` | LTE measurements |
| `CONFigure:WCDMa:SIGN:...` | WCDMA/HSPA signaling configuration |
| `SOURce:WCDMa:SIGN:...` | WCDMA/HSPA signal source control |
| `MEASure:WCDMa:SIGN:...` | WCDMA/HSPA measurements |
| `CONFigure:GSM:SIGN:...` | GSM/GPRS/EDGE signaling configuration |
| `SOURce:GSM:SIGN:...` | GSM/GPRS/EDGE signal source control |
| `MEASure:GSM:SIGN:...` | GSM/GPRS/EDGE measurements |
| `CONFigure:GPRF:...` | General purpose RF config |
| `SOURce:GPRF:...` | RF generator control |
| `CONFigure:FADing:...` | Fading channel config |

## Network Simulation Capabilities

### Fading Profiles

| Profile | Description | Doppler |
|---------|-------------|---------|
| STATIC | No fading | 0 Hz |
| EPA5 | Extended Pedestrian A | 5 Hz (~3 km/h) |
| EVA5 | Extended Vehicular A | 5 Hz |
| EVA70 | Extended Vehicular A | 70 Hz (~40 km/h) |
| ETU70 | Extended Typical Urban | 70 Hz |
| ETU300 | Extended Typical Urban | 300 Hz (~180 km/h) |
| HST | High-Speed Train | Variable |

### Predefined Scenarios

```python
# Available scenarios
NetworkSimulator.scenario_static_indoor()   # Indoor, no fading
NetworkSimulator.scenario_pedestrian()      # 3 km/h, EPA5
NetworkSimulator.scenario_vehicular()       # 40 km/h, EVA70
NetworkSimulator.scenario_high_speed()      # 180 km/h, ETU300
NetworkSimulator.scenario_urban_macro()     # Urban with interference
```

## Examples

See the `tests/` directory for complete examples:

- `example_lte_test.py` - Basic LTE signaling test
- `example_network_simulation.py` - Fading and mobility testing
- `example_rf_measurement.py` - General purpose RF measurements

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CMW500_HOST` | Instrument IP address | localhost |
| `CMW500_PORT` | SCPI port | 5025 |
| `CMW500_TIMEOUT` | Connection timeout | 10.0 |

### Config File Locations

The framework searches for config files in order:

1. `./cmw500_config.yaml`
2. `./config.yaml`
3. `./.cmw500.yaml`
4. `~/.cmw500/config.yaml`

## Error Handling

```python
from cmw500_test_framework.core.scpi import (
    SCPIError,
    SCPIConnectionError,
    SCPITimeoutError,
    SCPICommandError,
)

try:
    with CMW500Client("192.168.1.100") as client:
        client.lte.cell_on()
except SCPIConnectionError as e:
    print(f"Connection failed: {e}")
except SCPITimeoutError as e:
    print(f"Operation timed out: {e}")
except SCPICommandError as e:
    print(f"Command error {e.code}: {e.message}")
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest`
5. Submit a pull request

## License

MIT License - See LICENSE file for details.

## References

- [R&S CMW500 Product Page](https://www.rohde-schwarz.com/us/products/test-and-measurement/wireless-tester-network-emulator/cmw500-wideband-radio-communication-tester_63493-10844.html)
- [R&S SCPI Programming Guide](https://www.rohde-schwarz.com/us/driver-pages/remote-control/remote-programming-environments_231250.html)
- [3GPP TS 36.521-1 - LTE UE Conformance Testing](https://www.3gpp.org/specifications)
