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

# Measurement mode: "differential" (2-channel) or "inamp" (1-channel with amp)
POWER_DEFAULT_MODE = "differential"

# Saleae analog channel indices for differential measurement
POWER_DIFFERENTIAL_CHANNEL_A = 0  # Node A (host side of shunt)
POWER_DIFFERENTIAL_CHANNEL_B = 1  # Node B (DUT side of shunt)

# Default Saleae analog channel index for in-amp / single-channel measurement
POWER_ANALOG_CHANNEL = 0

# Instrumentation amplifier gain (V/V) — used only in "inamp" mode
POWER_DEFAULT_INAMP_GAIN = 20.0

# Continuous data transfer duration (seconds)
POWER_CONTINUOUS_TX_DURATION_SEC = 10.0

# Extra time beyond capture duration before killing subprocesses (seconds)
POWER_SUBPROCESS_GRACE_SEC = 2.0

# @pytest.mark.timeout() for power consumption tests
TEST_TIMEOUT_POWER = 300

# @pytest.mark.timeout() for QoS threshold tests (must sustain 6+ minutes)
TEST_TIMEOUT_QOS_THRESHOLD = 600

# @pytest.mark.timeout() for Baseball Rule tests (6-minute rule + setup)
TEST_TIMEOUT_BASEBALL_RULE = 600

# ---------------------------------------------------------------------------
# QoS fallback thresholds (Operational Performance Spec Section 5.4)
#
# These are the default NVM-configurable QoS thresholds.  When a parameter
# stays below its threshold for QOS_SUSTAINED_DURATION_SEC the firmware
# SHALL initiate service fallback.
# ---------------------------------------------------------------------------

QOS_LTE_RSRP_THRESHOLD_DBM = -120
QOS_LTE_SINR_THRESHOLD_DB = 0
QOS_HSPA_RSCP_THRESHOLD_DBM = -105
QOS_HSPA_ECIO_THRESHOLD_DB = -15
QOS_GPRS_RSSI_THRESHOLD_DBM = -100

# Duration a QoS parameter must remain below threshold to trigger fallback
QOS_SUSTAINED_DURATION_SEC = 360  # 6 minutes

# ---------------------------------------------------------------------------
# Baseball Rule (Operational Performance Spec Section 6.3)
#
# Three consecutive connection failures ("strikes") within the window
# trigger automatic service fallback.
# ---------------------------------------------------------------------------

BASEBALL_RULE_RETRY_WAIT_SEC = 120  # 2 minutes between retries
BASEBALL_RULE_MAX_STRIKES = 3
BASEBALL_RULE_WINDOW_SEC = 360  # 6 minutes total

# ---------------------------------------------------------------------------
# Service and mode fallback hierarchy
# (Operational Performance Spec Sections 6, 7; Provisioning Plan Section 5.13)
# ---------------------------------------------------------------------------

# Mode fallback priority — Cel_Mode 1-7
MODE_FALLBACK_PRIORITY = [
    "E-UTRAN",  # Mode 1: LTE
    "HSPA",     # Mode 2: 3G High Speed
    "HSUPA",    # Mode 3: 3G High Speed Uplink
    "HSDPA",    # Mode 4: 3G High Speed Downlink
    "UTRAN",    # Mode 5: 3G UMTS
    "EDGE",     # Mode 6: 2.5G Enhanced Data
    "WCDMA",    # Mode 7: 3G Legacy
]

# Service fallback tiers — Service_Index 1-4
SERVICE_FALLBACK_TIERS = ["primary", "tier1", "tier2", "global_default"]

# Fallback state machine timing (Operational Performance Spec Section 9.2)
PROFILE_SWITCH_MAX_SEC = 1.0     # eSIM profile switch < 1 second
MODE_SWITCH_MAX_SEC = 5.0        # RAT mode switch via AT+COPS < 5 seconds
SERVICE_RECOVERY_MAX_SEC = 10.0  # Service fallback recovery < 10 seconds
MODE_RECOVERY_MAX_SEC = 30.0     # Mode fallback recovery < 30 seconds

# ---------------------------------------------------------------------------
# Power consumption budgets (Component Selection Analysis)
# ---------------------------------------------------------------------------

# CELL_MOD_3V3_VCC rail budget for modem
POWER_MODEM_TYPICAL_BUDGET_MA = 350.0

# Power supply continuous output limit (shared across all rails)
POWER_SUPPLY_CONTINUOUS_MA = 760.0
