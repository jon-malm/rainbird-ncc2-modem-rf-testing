"""
Configuration Module

Handles loading and managing configuration from YAML files and command-line arguments.
Supports hierarchical configuration with defaults, environment variables, and overrides.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Try to import yaml, provide fallback if not available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    logger.warning("PyYAML not installed. YAML config files will not be supported.")


@dataclass
class InstrumentConfig:
    """Configuration for instrument connection."""
    host: str
    port: int = 5025
    timeout: float = 10.0
    auto_connect: bool = True


@dataclass
class RFConfig:
    """RF-related configuration."""
    frequency_mhz: float = 1950.0
    power_dbm: float = -60.0
    external_attenuation_db: float = 0.0
    rf_port: str = "RF1COM"


@dataclass
class LTEConfig:
    """LTE signaling configuration."""
    band: int = 1
    bandwidth_mhz: float = 10.0
    duplex_mode: str = "FDD"  # FDD or TDD
    dl_earfcn: int = 300
    cell_id: int = 1
    # Power settings
    rs_epre_dbm: float = -85.0
    pbch_power_dbm: float = -85.0
    # MIMO settings
    mimo_config: str = "1x1"  # 1x1, 2x2, 4x4
    transmission_mode: int = 1


@dataclass
class NRConfig:
    """5G NR configuration."""
    band: str = "n78"
    bandwidth_mhz: float = 100.0
    subcarrier_spacing_khz: int = 30
    duplex_mode: str = "TDD"
    ssb_frequency_mhz: float = 3600.0
    cell_id: int = 1


@dataclass
class MeasurementConfig:
    """Measurement configuration."""
    repetitions: int = 1
    averaging_count: int = 10
    timeout_seconds: float = 30.0
    result_format: str = "dBm"  # dBm, W, mW


@dataclass
class FadingConfig:
    """Fading channel configuration."""
    enabled: bool = False
    profile: str = "EPA5"  # EPA5, EVA5, EVA70, ETU70, etc.
    correlation: str = "LOW"  # LOW, MEDIUM, HIGH
    # Doppler frequency derived from profile or set manually
    doppler_hz: Optional[float] = None


@dataclass
class TestConfig:
    """Complete test configuration."""
    instrument: InstrumentConfig
    rf: RFConfig = field(default_factory=RFConfig)
    lte: LTEConfig = field(default_factory=LTEConfig)
    nr: NRConfig = field(default_factory=NRConfig)
    measurement: MeasurementConfig = field(default_factory=MeasurementConfig)
    fading: FadingConfig = field(default_factory=FadingConfig)


class Config:
    """
    Configuration manager supporting multiple sources.

    Priority (highest to lowest):
    1. Runtime overrides
    2. Command-line arguments
    3. Environment variables (CMW500_*)
    4. Config file
    5. Defaults

    Example:
        >>> config = Config.from_file("test_config.yaml")
        >>> config.instrument.host
        '192.168.1.100'

        >>> config = Config.from_dict({"instrument": {"host": "10.0.0.1"}})
    """

    DEFAULT_CONFIG_PATHS = [
        "cmw500_config.yaml",
        "config.yaml",
        ".cmw500.yaml",
        "~/.cmw500/config.yaml",
    ]

    # Environment variable prefix
    ENV_PREFIX = "CMW500_"

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        """
        Initialize configuration.

        Args:
            config_dict: Optional dictionary with configuration values
        """
        self._raw_config = config_dict or {}
        self._test_config: Optional[TestConfig] = None
        self._parse_config()

    def _parse_config(self) -> None:
        """Parse raw config dictionary into structured config."""
        # Apply environment variable overrides
        self._apply_env_overrides()

        # Create structured config
        instrument_cfg = self._raw_config.get("instrument", {})
        if not instrument_cfg.get("host"):
            # Check environment variable for host
            instrument_cfg["host"] = os.environ.get(
                f"{self.ENV_PREFIX}HOST", "localhost"
            )

        self._test_config = TestConfig(
            instrument=InstrumentConfig(
                host=instrument_cfg.get("host", "localhost"),
                port=instrument_cfg.get("port", 5025),
                timeout=instrument_cfg.get("timeout", 10.0),
                auto_connect=instrument_cfg.get("auto_connect", True),
            ),
            rf=self._parse_rf_config(self._raw_config.get("rf", {})),
            lte=self._parse_lte_config(self._raw_config.get("lte", {})),
            nr=self._parse_nr_config(self._raw_config.get("nr", {})),
            measurement=self._parse_measurement_config(
                self._raw_config.get("measurement", {})
            ),
            fading=self._parse_fading_config(self._raw_config.get("fading", {})),
        )

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to config."""
        env_mappings = {
            f"{self.ENV_PREFIX}HOST": ("instrument", "host"),
            f"{self.ENV_PREFIX}PORT": ("instrument", "port"),
            f"{self.ENV_PREFIX}TIMEOUT": ("instrument", "timeout"),
        }

        for env_var, path in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(self._raw_config, path, value)

    def _set_nested(
        self, d: Dict, path: tuple, value: Any
    ) -> None:
        """Set a nested dictionary value by path."""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value

    def _parse_rf_config(self, cfg: Dict) -> RFConfig:
        """Parse RF configuration section."""
        return RFConfig(
            frequency_mhz=cfg.get("frequency_mhz", 1950.0),
            power_dbm=cfg.get("power_dbm", -60.0),
            external_attenuation_db=cfg.get("external_attenuation_db", 0.0),
            rf_port=cfg.get("rf_port", "RF1COM"),
        )

    def _parse_lte_config(self, cfg: Dict) -> LTEConfig:
        """Parse LTE configuration section."""
        return LTEConfig(
            band=cfg.get("band", 1),
            bandwidth_mhz=cfg.get("bandwidth_mhz", 10.0),
            duplex_mode=cfg.get("duplex_mode", "FDD"),
            dl_earfcn=cfg.get("dl_earfcn", 300),
            cell_id=cfg.get("cell_id", 1),
            rs_epre_dbm=cfg.get("rs_epre_dbm", -85.0),
            pbch_power_dbm=cfg.get("pbch_power_dbm", -85.0),
            mimo_config=cfg.get("mimo_config", "1x1"),
            transmission_mode=cfg.get("transmission_mode", 1),
        )

    def _parse_nr_config(self, cfg: Dict) -> NRConfig:
        """Parse 5G NR configuration section."""
        return NRConfig(
            band=cfg.get("band", "n78"),
            bandwidth_mhz=cfg.get("bandwidth_mhz", 100.0),
            subcarrier_spacing_khz=cfg.get("subcarrier_spacing_khz", 30),
            duplex_mode=cfg.get("duplex_mode", "TDD"),
            ssb_frequency_mhz=cfg.get("ssb_frequency_mhz", 3600.0),
            cell_id=cfg.get("cell_id", 1),
        )

    def _parse_measurement_config(self, cfg: Dict) -> MeasurementConfig:
        """Parse measurement configuration section."""
        return MeasurementConfig(
            repetitions=cfg.get("repetitions", 1),
            averaging_count=cfg.get("averaging_count", 10),
            timeout_seconds=cfg.get("timeout_seconds", 30.0),
            result_format=cfg.get("result_format", "dBm"),
        )

    def _parse_fading_config(self, cfg: Dict) -> FadingConfig:
        """Parse fading configuration section."""
        return FadingConfig(
            enabled=cfg.get("enabled", False),
            profile=cfg.get("profile", "EPA5"),
            correlation=cfg.get("correlation", "LOW"),
            doppler_hz=cfg.get("doppler_hz"),
        )

    @property
    def instrument(self) -> InstrumentConfig:
        """Get instrument configuration."""
        return self._test_config.instrument

    @property
    def rf(self) -> RFConfig:
        """Get RF configuration."""
        return self._test_config.rf

    @property
    def lte(self) -> LTEConfig:
        """Get LTE configuration."""
        return self._test_config.lte

    @property
    def nr(self) -> NRConfig:
        """Get 5G NR configuration."""
        return self._test_config.nr

    @property
    def measurement(self) -> MeasurementConfig:
        """Get measurement configuration."""
        return self._test_config.measurement

    @property
    def fading(self) -> FadingConfig:
        """Get fading configuration."""
        return self._test_config.fading

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "Config":
        """
        Load configuration from a YAML file.

        Args:
            path: Path to YAML config file

        Returns:
            Config instance

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If YAML parsing fails
        """
        if not YAML_AVAILABLE:
            raise ImportError(
                "PyYAML is required for config file support. "
                "Install with: pip install pyyaml"
            )

        path = Path(path).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        try:
            with open(path, "r") as f:
                config_dict = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {path}")
            return cls(config_dict)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML config: {e}") from e

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "Config":
        """
        Create configuration from a dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            Config instance
        """
        return cls(config_dict)

    @classmethod
    def find_and_load(cls) -> "Config":
        """
        Find and load config from default locations.

        Searches in order:
        1. ./cmw500_config.yaml
        2. ./config.yaml
        3. ./.cmw500.yaml
        4. ~/.cmw500/config.yaml

        Returns:
            Config instance (with defaults if no file found)
        """
        for path_str in cls.DEFAULT_CONFIG_PATHS:
            path = Path(path_str).expanduser()
            if path.exists():
                return cls.from_file(path)

        logger.info("No config file found, using defaults")
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        return {
            "instrument": {
                "host": self.instrument.host,
                "port": self.instrument.port,
                "timeout": self.instrument.timeout,
                "auto_connect": self.instrument.auto_connect,
            },
            "rf": {
                "frequency_mhz": self.rf.frequency_mhz,
                "power_dbm": self.rf.power_dbm,
                "external_attenuation_db": self.rf.external_attenuation_db,
                "rf_port": self.rf.rf_port,
            },
            "lte": {
                "band": self.lte.band,
                "bandwidth_mhz": self.lte.bandwidth_mhz,
                "duplex_mode": self.lte.duplex_mode,
                "dl_earfcn": self.lte.dl_earfcn,
                "cell_id": self.lte.cell_id,
                "rs_epre_dbm": self.lte.rs_epre_dbm,
                "pbch_power_dbm": self.lte.pbch_power_dbm,
                "mimo_config": self.lte.mimo_config,
                "transmission_mode": self.lte.transmission_mode,
            },
            "nr": {
                "band": self.nr.band,
                "bandwidth_mhz": self.nr.bandwidth_mhz,
                "subcarrier_spacing_khz": self.nr.subcarrier_spacing_khz,
                "duplex_mode": self.nr.duplex_mode,
                "ssb_frequency_mhz": self.nr.ssb_frequency_mhz,
                "cell_id": self.nr.cell_id,
            },
            "measurement": {
                "repetitions": self.measurement.repetitions,
                "averaging_count": self.measurement.averaging_count,
                "timeout_seconds": self.measurement.timeout_seconds,
                "result_format": self.measurement.result_format,
            },
            "fading": {
                "enabled": self.fading.enabled,
                "profile": self.fading.profile,
                "correlation": self.fading.correlation,
                "doppler_hz": self.fading.doppler_hz,
            },
        }

    def save(self, path: Union[str, Path]) -> None:
        """
        Save configuration to a YAML file.

        Args:
            path: Output file path
        """
        if not YAML_AVAILABLE:
            raise ImportError("PyYAML is required for saving config files")

        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved configuration to {path}")
