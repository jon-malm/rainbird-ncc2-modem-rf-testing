# Power Consumption Testing

## Overview

This test suite measures USB device (modem) power consumption during various
operating states using a **Saleae Logic MSO** mixed-signal oscilloscope.
A shunt resistor on the USB VBUS line converts current draw into a voltage
measured by the MSO's analog input.  The captured waveform covers the full
state transition so registration spikes, PDP activation, and TX ramp-up are
all visible.

## Hardware Setup

### Required Equipment

- Saleae Logic MSO (connected to the test host via USB)
- USB breakout / passthrough board (exposes VBUS and GND lines)
- Current-sense shunt resistor (default: 0.01 Ω, ≥ 1 W)
- R&S CMW500 Base Station Simulator (existing test-bench equipment)
- Quectel EG21-G modem under test

### Wiring

```
Test Host USB ──► USB Breakout Board ──► Modem (DUT)
                       │
                   ┌───┴───┐
                   │ R_shunt│  (0.1 Ω on VBUS line)
                   └───┬───┘
                       │
              Saleae CH0 ──── across R_shunt
              Saleae GND ──── USB GND reference
```

1. Insert the USB breakout board between the test host and the modem.
2. Place the shunt resistor **in series** with the VBUS (5 V) line.
3. Connect Saleae analog channel 0 across the shunt resistor.
4. Connect the Saleae GND clip to the USB GND plane.

Current is computed as:

```
I = V_measured / R_shunt
```

### Probe Configuration

| Parameter        | Default        |
|------------------|----------------|
| Analog channel   | 0              |
| Sample rate      | 10 MSa/s       |
| Shunt resistance | 0.01 Ω         |

## Software Prerequisites

### Install the optional power dependency group

```bash
uv sync --group power
```

This installs:

- `saleae-mso-api` — Python API for Saleae Logic MSO
- `numpy` — used for waveform analysis (mean, min, max, std)

### Linux udev rules

On Linux, configure udev so the MSO device is accessible without root:

```bash
uv run python -m saleae.mso_api.utils.install_udev
```

### Saleae Logic software

Ensure the Saleae Logic 2 desktop application (≥ 2.4.20) is installed and
recognises the MSO device before running automated tests.

## Test Conditions

| # | Condition              | Modem State                                          |
|---|------------------------|------------------------------------------------------|
| 1 | Disconnected           | Radio off (`AT+CFUN=0`)                              |
| 2 | Connected idle         | Registered on LTE cell, no data transfer             |
| 3 | Transmit 1 KB          | Registered, data connection active, 1 KB ICMP ping   |
| 4 | Transmit 4 KB          | Registered, data connection active, 4 KB ICMP ping   |
| 5 | Transmit continuous    | Registered, data connection active, sustained ping    |

## Running the Tests

### Basic usage

```bash
uv run pytest tests/integration/test_power_consumption.py -v
```

When `saleae-mso-api` is **not** installed the module is silently skipped
at collection time — no SKIPPED noise in normal test output.

### CLI options

| Option               | Default  | Description                                      |
|----------------------|----------|--------------------------------------------------|
| `--logic-mso-serial` | (auto)   | Saleae Logic MSO serial number                   |
| `--shunt-resistance` | `0.01`   | Shunt resistance in Ohms                         |
| `--capture-duration` | `5.0`    | Analog capture duration per condition (seconds)  |
| `--skip-power`       | off      | Skip all power consumption tests                 |

### Examples

```bash
# Custom shunt and longer capture
uv run pytest tests/integration/test_power_consumption.py -v \
    --shunt-resistance 0.05 --capture-duration 20

# Skip power tests when running the full suite
uv run pytest tests/ -v --skip-power
```

## Capture Methodology

For each test condition the sequence is:

1. **Start MSO capture** — a timed analog capture begins in a background
   thread.  The capture is running *before* the modem condition is
   established so the full transition waveform is recorded.
2. **Establish modem condition** — turn radio off, register on the LTE
   cell, activate a data connection, or start transmitting data.
3. **Hold condition** — the modem remains in the target state for the
   remainder of the capture window.
4. **Capture completes** — the MSO timed capture finishes naturally (never
   terminated early).
5. **Compute current** — voltage samples are converted to current via
   `I = V / R_shunt`.  Average, minimum, maximum, and standard deviation
   are reported.

### Data transmission

- **1 KB / 4 KB**: `ping -I <modem_iface> -s 1024 -c N <target_ip>` where
  N = 1 for 1 KB and N = 4 for 4 KB.  The subprocess timeout is set to
  `capture_duration + 2 s` so it finishes naturally.
- **Continuous**: background `ping` at ~10 packets/second (1024-byte
  payload, 100 ms interval) for the full capture duration.  The subprocess
  is given `capture_duration + 2 s` to complete — it is **not** killed
  early.

The modem's USB ECM network interface (`usb0`, `wwan0`, etc.) is
auto-detected.  Traffic targets the DAU gateway IP.

## Interpreting Results

Each test logs a summary line:

```
TRANSMIT CONTINUOUS: avg=142.3 mA, min=38.1 mA, max=487.6 mA
```

| Metric            | Meaning                                            |
|-------------------|----------------------------------------------------|
| `avg_current_ma`  | Mean current over the full capture window           |
| `min_current_ma`  | Minimum instantaneous current (baseline / idle)     |
| `max_current_ma`  | Peak current (TX burst or registration spike)       |
| `std_current_ma`  | Standard deviation — indicates variability          |
| `avg_voltage_mv`  | Mean voltage across the shunt (for sanity checking) |

### Comparing runs

Run the tests multiple times and compare the average current for each
condition to identify regressions.  The MSO capture files are saved to
`tmp_path` (pytest temporary directory) and can be reloaded for offline
analysis.

## Configuration Reference

| Constant                          | Default      | Override CLI option    |
|-----------------------------------|--------------|-----------------------|
| `POWER_CAPTURE_DURATION_SEC`      | 5.0 s        | `--capture-duration`  |
| `POWER_DEFAULT_SHUNT_OHMS`        | 0.01 Ω       | `--shunt-resistance`  |
| `POWER_SAMPLE_RATE_HZ`            | 10,000,000   | (code only)           |
| `POWER_ANALOG_CHANNEL`            | 0            | (code only)           |
| `POWER_CONDITION_SETTLE_SEC`      | 3.0 s        | (code only)           |
| `POWER_CONTINUOUS_TX_DURATION_SEC` | 10.0 s      | (code only)           |
| `POWER_SUBPROCESS_GRACE_SEC`      | 2.0 s        | (code only)           |
| `TEST_TIMEOUT_POWER`              | 300 s        | (code only)           |

All constants are defined in `tests/constants.py`.
