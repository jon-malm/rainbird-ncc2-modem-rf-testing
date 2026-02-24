"""
Named constants for test timeouts and delays.

These values are used across the test suite to control timing behavior.
Grouping them here makes it easy to tune for different hardware setups
and avoids scattering magic numbers across test files.
"""

# ---------------------------------------------------------------------------
# time.sleep() delays -- used for hardware stabilization
# ---------------------------------------------------------------------------

# Radio cycle delays (AT+CFUN=0 / AT+CFUN=1 sequencing)
RADIO_OFF_SETTLE_SEC = 0.5
RADIO_ON_SETTLE_SEC = 1.0

# Polling interval during registration/deregistration wait loops
POLL_INTERVAL_SEC = 1.0
DEREG_POLL_INTERVAL_SEC = 0.5

# Cell/signal stabilization after state changes
CELL_STABILIZE_SEC = 1.0
SIGNAL_SETTLE_SEC = 2.0
CELL_DEACTIVATION_DETECT_SEC = 3.0

# WCDMA/RAT detection wait after cell switch
RAT_DETECTION_WAIT_SEC = 5.0

# Cell reselection wait (UE autonomously switching cells)
CELL_RESELECTION_SHORT_WAIT_SEC = 10.0
CELL_RESELECTION_WAIT_SEC = 15.0

# ---------------------------------------------------------------------------
# timeout_sec= parameters -- maximum wait for operations
# ---------------------------------------------------------------------------

# UE registration on cell (most common)
REGISTRATION_TIMEOUT_SEC = 60.0

# Recovery registration (post-outage, post-RAT-change)
RECOVERY_TIMEOUT_SEC = 90.0

# Prolonged outage recovery
PROLONGED_RECOVERY_TIMEOUT_SEC = 120.0

# UE deregistration detection
DEREGISTRATION_TIMEOUT_SEC = 30.0

# Data connection establishment
DATA_CONNECTION_TIMEOUT_SEC = 30.0

# CMW500-side UE registration detection
CMW_UE_REGISTRATION_TIMEOUT_SEC = 30.0

# ---------------------------------------------------------------------------
# AT command timeout= values (serial command response time)
# ---------------------------------------------------------------------------

AT_CMD_TIMEOUT = 5
AT_PDP_DEACTIVATE_TIMEOUT = 10
AT_PDP_ACTIVATE_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Throughput measurement durations
# ---------------------------------------------------------------------------

THROUGHPUT_DURATION_SEC = 10.0
THROUGHPUT_SHORT_DURATION_SEC = 5.0

# ---------------------------------------------------------------------------
# @pytest.mark.timeout() decorator values (overall test timeouts)
# ---------------------------------------------------------------------------

TEST_TIMEOUT_STANDARD = 120
TEST_TIMEOUT_MEDIUM = 180
TEST_TIMEOUT_LONG = 240
TEST_TIMEOUT_EXTENDED = 300
TEST_TIMEOUT_MAXIMUM = 360

# ---------------------------------------------------------------------------
# Test-specific durations
# ---------------------------------------------------------------------------

PROLONGED_OUTAGE_DURATION_SEC = 120
BRIEF_OUTAGE_DURATION_SEC = 3
INTERMITTENT_RECOVERY_WAIT_SEC = 30
RAPID_CHANGE_INTERVAL_SEC = 1.0

# UE measurement report polling (CMW500 returns NAV until first report)
UE_REPORT_POLL_TIMEOUT_SEC = 20.0
UE_REPORT_POLL_INTERVAL_SEC = 0.5

# ---------------------------------------------------------------------------
# Power consumption measurement (requires optional saleae-mso-api)
# ---------------------------------------------------------------------------

# Duration of analog capture for each modem condition (seconds)
POWER_CAPTURE_DURATION_SEC = 5.0

# Settle time after establishing a modem condition before starting capture
POWER_CONDITION_SETTLE_SEC = 3.0

# Saleae MSO analog sample rate (Hz) -- 10 MSa/s for power envelope
POWER_SAMPLE_RATE_HZ = 10_000_000

# Default shunt resistance in Ohms for current measurement (I = V / R)
POWER_DEFAULT_SHUNT_OHMS = 0.01

# Measurement mode: "differential" (2-ch) or "inamp" (1-ch with amplifier)
POWER_DEFAULT_MODE = "differential"

# Instrumentation amplifier gain (V/V) for inamp mode
POWER_DEFAULT_INAMP_GAIN = 20.0

# Default Saleae analog channel index for VBUS measurement
POWER_ANALOG_CHANNEL = 0

# Differential mode channel indices (high-side / low-side of shunt)
POWER_DIFFERENTIAL_CHANNEL_A = 0
POWER_DIFFERENTIAL_CHANNEL_B = 1

# Continuous data transfer duration (seconds)
POWER_CONTINUOUS_TX_DURATION_SEC = 10.0

# Extra time beyond capture duration before killing subprocesses (seconds)
POWER_SUBPROCESS_GRACE_SEC = 2.0

# Modem rail typical current budget (CELL_MOD_3V3_VCC) in milliamps
POWER_MODEM_TYPICAL_BUDGET_MA = 350.0

# PSU continuous current limit (USB spec) in milliamps
POWER_SUPPLY_CONTINUOUS_MA = 500.0

# @pytest.mark.timeout() for power consumption tests
TEST_TIMEOUT_POWER = 300
