# CMW500 RF Testing Suite

Python tools and test framework for communication and testing with Rohde & Schwarz CMW500 Wideband Radio Communication Tester.

## Components

### 1. CMW500 LAN Query Application (`cmw500_query.py`)

Simple utility to query CMW500 instrument identification via LAN.

```bash
python cmw500_query.py <CMW500_IP_ADDRESS>
```

### 2. CMW500 Test Framework (`cmw500_test_framework/`)

Comprehensive Python test framework for network simulation and RF testing. Features include:

- **LTE Signaling Control**: Cell configuration, UE connection management, RF measurements
- **Network Simulation**: Fading channels, path loss, mobility scenarios
- **General Purpose RF**: Signal generation, power measurements, spectrum analysis
- **Configuration Management**: YAML configs, CLI interface, environment variables

See [cmw500_test_framework/README.md](cmw500_test_framework/README.md) for complete documentation.

## Quick Start

### Installation

```bash
# Install test framework with YAML support
cd cmw500_test_framework
pip install -e ".[yaml]"
```

### Basic Usage

```python
from cmw500_test_framework import CMW500Client

with CMW500Client("192.168.1.100") as client:
    # Get instrument info
    info = client.get_system_info()
    print(f"Connected to: {info.model}")

    # Configure and enable LTE cell
    client.lte.configure_cell(band=1, bandwidth_mhz=10)
    client.lte.set_dl_power(rs_epre_dbm=-85)
    client.lte.cell_on()

    # Wait for UE and measure
    client.lte.wait_for_attach(timeout=60)
    tx_power = client.lte.measure_tx_power()
    print(f"TX Power: {tx_power.pusch_power_dbm} dBm")

    client.lte.cell_off()
```

### CLI Usage

```bash
# Show instrument info
cmw500-cli info 192.168.1.100

# Control LTE cell
cmw500-cli lte-cell 192.168.1.100 --on --band 1

# Load network simulation scenario
cmw500-cli scenario 192.168.1.100 vehicular --enable-fading

# Perform measurements
cmw500-cli measure 192.168.1.100 power -f 1950
```

## Requirements

- Python 3.8+
- Network access to CMW500
- Optional: PyYAML for config file support

## Project Structure

```
rainbird-ncc2-modem-rf-testing/
├── cmw500_query.py              # Simple query utility
├── cmw500_test_framework/       # Full test framework
│   ├── core/                    # Core modules (client, scpi, config)
│   ├── applications/            # Application modules (lte, gprf, network_sim)
│   ├── utils/                   # Utility functions
│   ├── tests/                   # Example test scripts
│   ├── configs/examples/        # Example configuration files
│   ├── cli.py                   # Command-line interface
│   └── README.md                # Framework documentation
├── README.md                    # This file
└── requirements.txt             # Dependencies
```

## CMW500 Capabilities

The CMW500 supports:

- **Cellular Technologies**: LTE/LTE-A, WCDMA, GSM, CDMA2000
- **5G NR**: With CMX500 extension
- **Wireless Connectivity**: WLAN, Bluetooth
- **Measurements**: TX power, ACLR, EVM, spectrum analysis
- **Network Simulation**: Cell emulation, fading channels, MIMO
- **Carrier Aggregation**: Up to 8 DL component carriers

## References

- [R&S CMW500 Product Page](https://www.rohde-schwarz.com/us/products/test-and-measurement/wireless-tester-network-emulator/cmw500-wideband-radio-communication-tester_63493-10844.html)
- [R&S SCPI Remote Control](https://www.rohde-schwarz.com/us/driver-pages/remote-control/remote-programming-environments_231250.html)
- [CMW500 Manual Overview](https://www.rohde-schwarz.com/us/manual/cmw500_overview/)
