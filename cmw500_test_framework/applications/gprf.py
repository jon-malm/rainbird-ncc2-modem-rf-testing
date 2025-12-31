"""
General Purpose RF Module

Controls the General Purpose RF (GPRF) functionality on the CMW500.
Provides non-signaling RF generation and analysis capabilities.

Use cases:
- CW signal generation
- RF power measurements
- Spectrum analysis
- Non-signaling device testing

SCPI Command Reference:
- CONFigure:GPRF:... - Configuration commands
- SOURce:GPRF:... - Generator commands
- FETCh:GPRF:... - Measurement fetch commands
"""

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from ..core.client import CMW500Client

logger = logging.getLogger(__name__)


class GeneratorState(Enum):
    """RF generator state."""
    OFF = "OFF"
    ON = "ON"


class MeasurementState(Enum):
    """Measurement state."""
    OFF = "OFF"
    ON = "ON"
    RUNNING = "RUN"


class ModulationType(Enum):
    """Modulation types for generator."""
    CW = "CW"
    AM = "AM"
    FM = "FM"
    PM = "PM"
    PULSE = "PULSe"


class TriggerSource(Enum):
    """Trigger source options."""
    FREE_RUN = "FREE"
    INTERNAL = "INT"
    EXTERNAL = "EXT"
    POWER = "POW"


@dataclass
class PowerMeasurement:
    """Power measurement result."""
    reliability: str
    power_dbm: float
    min_power_dbm: float
    max_power_dbm: float
    std_dev: float

    @property
    def is_valid(self) -> bool:
        return self.reliability in ("OK", "0")


@dataclass
class SpectrumResult:
    """Spectrum analysis result."""
    reliability: str
    center_frequency_hz: float
    peak_power_dbm: float
    channel_power_dbm: float


class GeneralPurposeRF:
    """
    General Purpose RF control for CMW500.

    Provides methods for:
    - RF signal generation (CW, modulated)
    - Power measurements
    - Spectrum analysis
    - Frequency measurements

    Example:
        >>> client = CMW500Client("192.168.1.100")
        >>> client.connect()
        >>>
        >>> # Generate CW signal
        >>> client.gprf.configure_generator(frequency_mhz=1950, power_dbm=-30)
        >>> client.gprf.generator_on()
        >>>
        >>> # Measure power
        >>> client.gprf.configure_power_measurement(frequency_mhz=1950)
        >>> result = client.gprf.measure_power()
        >>> print(f"Power: {result.power_dbm} dBm")
    """

    # SCPI subsystem prefixes
    CONF_GEN_PREFIX = "CONFigure:GPRF:GEN"
    CONF_MEAS_PREFIX = "CONFigure:GPRF:MEAS"
    SOURCE_PREFIX = "SOURce:GPRF:GEN"
    FETCH_PREFIX = "FETCh:GPRF:MEAS"
    READ_PREFIX = "READ:GPRF:MEAS"

    def __init__(self, client: "CMW500Client"):
        """
        Initialize GPRF module.

        Args:
            client: CMW500Client instance
        """
        self._client = client

    @property
    def scpi(self):
        """Get SCPI connection."""
        return self._client.scpi

    # =========================================================================
    # RF Generator Configuration
    # =========================================================================

    def configure_generator(
        self,
        frequency_mhz: float,
        power_dbm: float,
        rf_port: str = "RF1COM",
        modulation: str = "CW",
    ) -> None:
        """
        Configure RF generator settings.

        Args:
            frequency_mhz: Output frequency in MHz
            power_dbm: Output power in dBm
            rf_port: RF output port
            modulation: Modulation type (CW, AM, FM, PM)
        """
        logger.info(f"Configuring generator: {frequency_mhz} MHz, {power_dbm} dBm")

        # Set RF output port/connector
        self.scpi.write(f"{self.CONF_GEN_PREFIX}:RFSettings:CONNector {rf_port}")

        # Set frequency (convert to Hz for SCPI)
        freq_hz = frequency_mhz * 1e6
        self.scpi.write(f"{self.SOURCE_PREFIX}:RFSettings:FREQuency {freq_hz}")

        # Set output power level
        self.scpi.write(f"{self.SOURCE_PREFIX}:RFSettings:LEVel {power_dbm}")

        # Set modulation type
        self.scpi.write(f"{self.SOURCE_PREFIX}:MODulation:TYPE {modulation}")

    def set_generator_frequency(self, frequency_mhz: float) -> None:
        """Set generator frequency in MHz."""
        freq_hz = frequency_mhz * 1e6
        self.scpi.write(f"{self.SOURCE_PREFIX}:RFSettings:FREQuency {freq_hz}")

    def set_generator_power(self, power_dbm: float) -> None:
        """Set generator output power in dBm."""
        self.scpi.write(f"{self.SOURCE_PREFIX}:RFSettings:LEVel {power_dbm}")

    def get_generator_settings(self) -> Dict[str, float]:
        """Get current generator settings."""
        freq = self.scpi.query(f"{self.SOURCE_PREFIX}:RFSettings:FREQuency?").as_float()
        power = self.scpi.query(f"{self.SOURCE_PREFIX}:RFSettings:LEVel?").as_float()

        return {
            "frequency_mhz": freq / 1e6,
            "power_dbm": power,
        }

    def generator_on(self) -> None:
        """Turn on RF generator."""
        logger.info("Turning RF generator ON")
        self.scpi.write(f"{self.SOURCE_PREFIX}:STATe ON")
        time.sleep(0.5)

    def generator_off(self) -> None:
        """Turn off RF generator."""
        logger.info("Turning RF generator OFF")
        self.scpi.write(f"{self.SOURCE_PREFIX}:STATe OFF")

    def get_generator_state(self) -> str:
        """Get generator state."""
        return self.scpi.query(f"{self.SOURCE_PREFIX}:STATe?").value

    # =========================================================================
    # Modulation Configuration
    # =========================================================================

    def configure_am_modulation(
        self,
        depth_percent: float = 30.0,
        frequency_hz: float = 1000.0,
    ) -> None:
        """
        Configure AM modulation.

        Args:
            depth_percent: Modulation depth (0-100%)
            frequency_hz: Modulation frequency
        """
        self.scpi.write(f"{self.SOURCE_PREFIX}:MODulation:TYPE AM")
        self.scpi.write(f"{self.SOURCE_PREFIX}:MODulation:AM:DEPTh {depth_percent}")
        self.scpi.write(f"{self.SOURCE_PREFIX}:MODulation:AM:FREQuency {frequency_hz}")

    def configure_fm_modulation(
        self,
        deviation_hz: float = 75000.0,
        frequency_hz: float = 1000.0,
    ) -> None:
        """
        Configure FM modulation.

        Args:
            deviation_hz: Frequency deviation in Hz
            frequency_hz: Modulation frequency
        """
        self.scpi.write(f"{self.SOURCE_PREFIX}:MODulation:TYPE FM")
        self.scpi.write(f"{self.SOURCE_PREFIX}:MODulation:FM:DEViation {deviation_hz}")
        self.scpi.write(f"{self.SOURCE_PREFIX}:MODulation:FM:FREQuency {frequency_hz}")

    # =========================================================================
    # Power Measurement Configuration
    # =========================================================================

    def configure_power_measurement(
        self,
        frequency_mhz: float,
        expected_power_dbm: float = -30.0,
        rf_port: str = "RF1COM",
        bandwidth_mhz: float = 10.0,
    ) -> None:
        """
        Configure power measurement settings.

        Args:
            frequency_mhz: Center frequency in MHz
            expected_power_dbm: Expected input power (for auto-ranging)
            rf_port: RF input port
            bandwidth_mhz: Measurement bandwidth in MHz
        """
        logger.info(f"Configuring power measurement: {frequency_mhz} MHz")

        # Set input connector
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:RFSettings:CONNector {rf_port}")

        # Set frequency
        freq_hz = frequency_mhz * 1e6
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:RFSettings:FREQuency {freq_hz}")

        # Set expected power for optimal ranging
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:RFSettings:ENPower {expected_power_dbm}")

        # Set measurement bandwidth
        bw_hz = bandwidth_mhz * 1e6
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:POWer:FILTer:BANDwidth {bw_hz}")

    def configure_measurement_trigger(
        self,
        source: str = "FREE",
        level_dbm: Optional[float] = None,
        delay_us: float = 0,
    ) -> None:
        """
        Configure measurement trigger.

        Args:
            source: Trigger source (FREE, INT, EXT, POW)
            level_dbm: Power trigger level (for POW source)
            delay_us: Trigger delay in microseconds
        """
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:POWer:TRIGger:SOURce {source}")

        if source == "POW" and level_dbm is not None:
            self.scpi.write(f"{self.CONF_MEAS_PREFIX}:POWer:TRIGger:LEVel {level_dbm}")

        if delay_us > 0:
            self.scpi.write(f"{self.CONF_MEAS_PREFIX}:POWer:TRIGger:DELay {delay_us}US")

    # =========================================================================
    # Power Measurements
    # =========================================================================

    def measure_power(self, timeout: float = 10.0) -> PowerMeasurement:
        """
        Perform power measurement.

        Args:
            timeout: Measurement timeout in seconds

        Returns:
            PowerMeasurement result
        """
        logger.info("Measuring power")

        # Start measurement
        self.scpi.write(f"INITiate:GPRF:MEAS:POWer")
        self.scpi.wait_for_completion(timeout=timeout)

        # Fetch results
        result = self.scpi.query(f"{self.FETCH_PREFIX}:POWer:AVERage?")
        parts = result.as_list()

        return PowerMeasurement(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            power_dbm=float(parts[1]) if len(parts) > 1 else float('nan'),
            min_power_dbm=float(parts[2]) if len(parts) > 2 else float('nan'),
            max_power_dbm=float(parts[3]) if len(parts) > 3 else float('nan'),
            std_dev=float(parts[4]) if len(parts) > 4 else float('nan'),
        )

    def measure_power_continuous(
        self,
        count: int = 10,
        interval_ms: float = 100,
    ) -> List[float]:
        """
        Perform multiple power measurements.

        Args:
            count: Number of measurements
            interval_ms: Interval between measurements

        Returns:
            List of power measurements in dBm
        """
        results = []
        for _ in range(count):
            measurement = self.measure_power()
            if measurement.is_valid:
                results.append(measurement.power_dbm)
            time.sleep(interval_ms / 1000)
        return results

    def measure_power_vs_time(
        self,
        duration_ms: float = 100,
        sample_rate: str = "FAST",
    ) -> Dict[str, any]:
        """
        Measure power vs time (for burst signals).

        Args:
            duration_ms: Capture duration in milliseconds
            sample_rate: Sample rate (FAST, NORMal, SLOW)

        Returns:
            Dictionary with time-domain power data
        """
        # Configure time-domain measurement
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:POWer:TDOMain:DURation {duration_ms}MS")
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:POWer:TDOMain:SRATE {sample_rate}")

        # Execute measurement
        self.scpi.write("INITiate:GPRF:MEAS:POWer")
        self.scpi.wait_for_completion(timeout=30)

        # Fetch statistics
        result = self.scpi.query(f"{self.FETCH_PREFIX}:POWer:TDOMain:AVERage?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "avg_power_dbm": float(parts[1]) if len(parts) > 1 else float('nan'),
            "peak_power_dbm": float(parts[2]) if len(parts) > 2 else float('nan'),
            "min_power_dbm": float(parts[3]) if len(parts) > 3 else float('nan'),
        }

    # =========================================================================
    # Spectrum Measurements
    # =========================================================================

    def configure_spectrum_measurement(
        self,
        center_frequency_mhz: float,
        span_mhz: float = 10.0,
        rbw_khz: float = 30.0,
        vbw_khz: float = 100.0,
        detector: str = "RMS",
    ) -> None:
        """
        Configure spectrum analyzer measurement.

        Args:
            center_frequency_mhz: Center frequency in MHz
            span_mhz: Frequency span in MHz
            rbw_khz: Resolution bandwidth in kHz
            vbw_khz: Video bandwidth in kHz
            detector: Detector type (RMS, PEAK, AVERage)
        """
        logger.info(f"Configuring spectrum: {center_frequency_mhz} MHz, span {span_mhz} MHz")

        freq_hz = center_frequency_mhz * 1e6
        span_hz = span_mhz * 1e6
        rbw_hz = rbw_khz * 1e3
        vbw_hz = vbw_khz * 1e3

        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:SPECtrum:FREQuency:CENTer {freq_hz}")
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:SPECtrum:FREQuency:SPAN {span_hz}")
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:SPECtrum:BANDwidth:RESolution {rbw_hz}")
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:SPECtrum:BANDwidth:VIDeo {vbw_hz}")
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:SPECtrum:DETector {detector}")

    def measure_spectrum_peak(self) -> SpectrumResult:
        """
        Measure spectrum and find peak.

        Returns:
            SpectrumResult with peak frequency and power
        """
        logger.info("Measuring spectrum peak")

        # Execute measurement
        self.scpi.write("INITiate:GPRF:MEAS:SPECtrum")
        self.scpi.wait_for_completion(timeout=30)

        # Fetch peak results
        result = self.scpi.query(f"{self.FETCH_PREFIX}:SPECtrum:PEAKsearch?")
        parts = result.as_list()

        return SpectrumResult(
            reliability=parts[0] if len(parts) > 0 else "NAV",
            center_frequency_hz=float(parts[1]) if len(parts) > 1 else float('nan'),
            peak_power_dbm=float(parts[2]) if len(parts) > 2 else float('nan'),
            channel_power_dbm=float(parts[3]) if len(parts) > 3 else float('nan'),
        )

    # =========================================================================
    # Frequency Measurement
    # =========================================================================

    def measure_frequency(self) -> Dict[str, float]:
        """
        Measure signal frequency.

        Returns:
            Dictionary with frequency measurement results
        """
        logger.info("Measuring frequency")

        self.scpi.write("INITiate:GPRF:MEAS:FREQuency")
        self.scpi.wait_for_completion(timeout=10)

        result = self.scpi.query(f"{self.FETCH_PREFIX}:FREQuency?")
        parts = result.as_list()

        return {
            "reliability": parts[0] if len(parts) > 0 else "NAV",
            "frequency_hz": float(parts[1]) if len(parts) > 1 else float('nan'),
            "frequency_error_hz": float(parts[2]) if len(parts) > 2 else float('nan'),
        }

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def auto_level(self) -> float:
        """
        Auto-level the input signal.

        Returns:
            Detected power level in dBm
        """
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:RFSettings:ENPower:AUTO ONCE")
        self.scpi.wait_for_completion(timeout=10)

        return self.scpi.query(f"{self.CONF_MEAS_PREFIX}:RFSettings:ENPower?").as_float()

    def set_external_attenuation(self, attenuation_db: float) -> None:
        """
        Set external attenuation compensation.

        Args:
            attenuation_db: External attenuation in dB
        """
        self.scpi.write(f"{self.CONF_MEAS_PREFIX}:RFSettings:EATTenuation {attenuation_db}")
        self.scpi.write(f"{self.CONF_GEN_PREFIX}:RFSettings:EATTenuation {attenuation_db}")
