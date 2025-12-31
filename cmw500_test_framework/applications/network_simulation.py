"""
Network Simulation Module

Provides network simulation capabilities on the CMW500, including:
- Cell emulation with configurable parameters
- Fading channel simulation
- Multi-cell scenarios
- Handover simulation
- Network impairment testing

This module coordinates LTE/5G signaling with channel fading
to create realistic network conditions for device testing.
"""

import logging
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

if TYPE_CHECKING:
    from ..core.client import CMW500Client

logger = logging.getLogger(__name__)


class FadingProfile(Enum):
    """Standard 3GPP fading profiles."""
    # LTE Extended Pedestrian A
    EPA5 = "EPA5"      # 5 Hz Doppler
    # LTE Extended Vehicular A
    EVA5 = "EVA5"      # 5 Hz Doppler
    EVA70 = "EVA70"    # 70 Hz Doppler
    # LTE Extended Typical Urban
    ETU70 = "ETU70"    # 70 Hz Doppler
    ETU300 = "ETU300"  # 300 Hz Doppler
    # High-speed train
    HST = "HST"        # High-speed train scenario
    # Static (no fading)
    STATIC = "STATIC"
    # AWGN (additive white gaussian noise)
    AWGN = "AWGN"


class CorrelationType(Enum):
    """MIMO antenna correlation."""
    LOW = "LOW"
    MEDIUM = "MED"
    MEDIUM_A = "MEDA"
    HIGH = "HIGH"


class PropagationCondition(Enum):
    """Propagation conditions for testing."""
    STATIC = "STATIC"
    MULTI_PATH = "MULTIPATH"
    MOVING = "MOVING"
    HIGH_SPEED = "HIGHSPEED"


@dataclass
class FadingConfig:
    """Fading channel configuration."""
    profile: FadingProfile = FadingProfile.EPA5
    correlation: CorrelationType = CorrelationType.LOW
    doppler_hz: Optional[float] = None  # Override profile default
    # Path-specific settings
    awgn_enabled: bool = False
    awgn_snr_db: float = 30.0
    # Timing
    seed: int = 0  # 0 = random seed


@dataclass
class CellConfig:
    """Cell configuration for network simulation."""
    cell_id: int
    band: int
    frequency_mhz: float
    power_dbm: float
    enabled: bool = True
    # Optional neighbor cell settings
    is_neighbor: bool = False
    handover_threshold_db: float = -3.0


@dataclass
class NetworkScenario:
    """Complete network simulation scenario."""
    name: str
    description: str = ""
    cells: List[CellConfig] = field(default_factory=list)
    fading: Optional[FadingConfig] = None
    # Impairments
    path_loss_db: float = 0.0
    interference_enabled: bool = False
    interference_level_dbm: float = -100.0


class NetworkSimulator:
    """
    Network simulation controller for CMW500.

    Provides high-level methods for:
    - Setting up network simulation scenarios
    - Configuring fading channels
    - Managing multi-cell scenarios
    - Simulating network impairments
    - Handover testing

    Example:
        >>> client = CMW500Client("192.168.1.100")
        >>> client.connect()
        >>>
        >>> # Create network simulator
        >>> from cmw500_test_framework.applications import NetworkSimulator
        >>> sim = NetworkSimulator(client)
        >>>
        >>> # Configure fading
        >>> sim.configure_fading(profile="EVA70", correlation="LOW")
        >>> sim.enable_fading()
        >>>
        >>> # Or load a predefined scenario
        >>> sim.load_scenario(NetworkScenario(
        ...     name="Urban Mobility",
        ...     cells=[CellConfig(cell_id=1, band=1, frequency_mhz=1950, power_dbm=-85)],
        ...     fading=FadingConfig(profile=FadingProfile.EVA70)
        ... ))
    """

    # SCPI prefixes for fading simulator
    FADING_PREFIX = "CONFigure:FADing"
    FADING_STATE_PREFIX = "SOURce:FADing"

    def __init__(self, client: "CMW500Client"):
        """
        Initialize network simulator.

        Args:
            client: CMW500Client instance
        """
        self._client = client
        self._current_scenario: Optional[NetworkScenario] = None
        self._fading_enabled = False

    @property
    def scpi(self):
        """Get SCPI connection."""
        return self._client.scpi

    @property
    def lte(self):
        """Get LTE signaling module."""
        return self._client.lte

    # =========================================================================
    # Fading Channel Configuration
    # =========================================================================

    def configure_fading(
        self,
        profile: Union[str, FadingProfile] = "EPA5",
        correlation: Union[str, CorrelationType] = "LOW",
        doppler_hz: Optional[float] = None,
    ) -> None:
        """
        Configure fading channel parameters.

        Args:
            profile: Fading profile (EPA5, EVA5, EVA70, ETU70, etc.)
            correlation: MIMO correlation (LOW, MEDIUM, HIGH)
            doppler_hz: Override Doppler frequency (Hz)
        """
        # Convert enum to string if needed
        if isinstance(profile, FadingProfile):
            profile = profile.value
        if isinstance(correlation, CorrelationType):
            correlation = correlation.value

        logger.info(f"Configuring fading: {profile}, correlation={correlation}")

        # Set fading profile
        self.scpi.write(f"{self.FADING_PREFIX}:PROFile {profile}")

        # Set correlation
        self.scpi.write(f"{self.FADING_PREFIX}:CORRelation {correlation}")

        # Set Doppler if specified
        if doppler_hz is not None:
            self.scpi.write(f"{self.FADING_PREFIX}:DOPPler {doppler_hz}")

    def enable_fading(self) -> None:
        """Enable fading channel."""
        logger.info("Enabling fading channel")
        self.scpi.write(f"{self.FADING_STATE_PREFIX}:STATe ON")
        self._fading_enabled = True
        time.sleep(0.5)

    def disable_fading(self) -> None:
        """Disable fading channel."""
        logger.info("Disabling fading channel")
        self.scpi.write(f"{self.FADING_STATE_PREFIX}:STATe OFF")
        self._fading_enabled = False

    def get_fading_state(self) -> bool:
        """Check if fading is enabled."""
        state = self.scpi.query(f"{self.FADING_STATE_PREFIX}:STATe?").value
        return state == "ON"

    def configure_awgn(
        self,
        snr_db: float = 30.0,
        enabled: bool = True,
    ) -> None:
        """
        Configure AWGN (Additive White Gaussian Noise).

        Args:
            snr_db: Signal-to-noise ratio in dB
            enabled: Enable/disable AWGN
        """
        logger.info(f"Configuring AWGN: SNR={snr_db} dB, enabled={enabled}")

        self.scpi.write(f"{self.FADING_PREFIX}:AWGN:SNR {snr_db}")
        state = "ON" if enabled else "OFF"
        self.scpi.write(f"{self.FADING_PREFIX}:AWGN:STATe {state}")

    def set_fading_seed(self, seed: int) -> None:
        """
        Set fading random seed for reproducibility.

        Args:
            seed: Random seed (0 = random)
        """
        self.scpi.write(f"{self.FADING_PREFIX}:SEED {seed}")

    # =========================================================================
    # Path Loss / Attenuation
    # =========================================================================

    def set_path_loss(
        self,
        loss_db: float,
        direction: str = "BOTH",
    ) -> None:
        """
        Set simulated path loss.

        Args:
            loss_db: Path loss in dB
            direction: "DL" (downlink), "UL" (uplink), or "BOTH"
        """
        logger.info(f"Setting path loss: {loss_db} dB ({direction})")

        if direction.upper() in ("DL", "BOTH"):
            self.scpi.write(f"CONFigure:LTE:SIGN:RFSettings:DL:PATHloss {loss_db}")

        if direction.upper() in ("UL", "BOTH"):
            self.scpi.write(f"CONFigure:LTE:SIGN:RFSettings:UL:PATHloss {loss_db}")

    def simulate_distance(
        self,
        distance_km: float,
        frequency_mhz: float = 1950.0,
        model: str = "FREE_SPACE",
    ) -> float:
        """
        Calculate and apply path loss based on distance.

        Args:
            distance_km: Distance in kilometers
            frequency_mhz: Carrier frequency
            model: Path loss model (FREE_SPACE, COST231, etc.)

        Returns:
            Calculated path loss in dB
        """
        # Free space path loss calculation
        # FSPL(dB) = 20*log10(d) + 20*log10(f) + 20*log10(4*pi/c)
        # Simplified: FSPL(dB) = 32.45 + 20*log10(f_MHz) + 20*log10(d_km)
        import math

        if model == "FREE_SPACE":
            fspl = 32.45 + 20 * math.log10(frequency_mhz) + 20 * math.log10(distance_km)
        else:
            # Default to free space for now
            fspl = 32.45 + 20 * math.log10(frequency_mhz) + 20 * math.log10(distance_km)

        logger.info(f"Calculated path loss for {distance_km} km: {fspl:.1f} dB")
        self.set_path_loss(fspl)
        return fspl

    # =========================================================================
    # Scenario Management
    # =========================================================================

    def load_scenario(self, scenario: NetworkScenario) -> None:
        """
        Load a complete network simulation scenario.

        Args:
            scenario: NetworkScenario configuration
        """
        logger.info(f"Loading scenario: {scenario.name}")

        self._current_scenario = scenario

        # Configure primary cell
        if scenario.cells:
            primary = scenario.cells[0]
            self.lte.configure_cell(
                band=primary.band,
                cell_id=primary.cell_id,
            )
            self.lte.set_dl_power(rs_epre_dbm=primary.power_dbm)

        # Configure fading if specified
        if scenario.fading:
            self.configure_fading(
                profile=scenario.fading.profile,
                correlation=scenario.fading.correlation,
                doppler_hz=scenario.fading.doppler_hz,
            )

            if scenario.fading.awgn_enabled:
                self.configure_awgn(
                    snr_db=scenario.fading.awgn_snr_db,
                    enabled=True,
                )

        # Apply path loss
        if scenario.path_loss_db > 0:
            self.set_path_loss(scenario.path_loss_db)

    def get_current_scenario(self) -> Optional[NetworkScenario]:
        """Get currently loaded scenario."""
        return self._current_scenario

    # =========================================================================
    # Predefined Test Scenarios
    # =========================================================================

    @staticmethod
    def scenario_static_indoor() -> NetworkScenario:
        """Create static indoor test scenario (no fading)."""
        return NetworkScenario(
            name="Static Indoor",
            description="Indoor stationary device, no fading",
            cells=[
                CellConfig(
                    cell_id=1,
                    band=1,
                    frequency_mhz=1950.0,
                    power_dbm=-70.0,
                )
            ],
            fading=FadingConfig(profile=FadingProfile.STATIC),
            path_loss_db=60.0,
        )

    @staticmethod
    def scenario_pedestrian() -> NetworkScenario:
        """Create pedestrian mobility scenario (3 km/h)."""
        return NetworkScenario(
            name="Pedestrian",
            description="Low speed pedestrian scenario, EPA5 fading",
            cells=[
                CellConfig(
                    cell_id=1,
                    band=1,
                    frequency_mhz=1950.0,
                    power_dbm=-85.0,
                )
            ],
            fading=FadingConfig(
                profile=FadingProfile.EPA5,
                correlation=CorrelationType.LOW,
            ),
            path_loss_db=70.0,
        )

    @staticmethod
    def scenario_vehicular() -> NetworkScenario:
        """Create vehicular mobility scenario (30 km/h)."""
        return NetworkScenario(
            name="Vehicular",
            description="Medium speed vehicular scenario, EVA70 fading",
            cells=[
                CellConfig(
                    cell_id=1,
                    band=1,
                    frequency_mhz=1950.0,
                    power_dbm=-85.0,
                )
            ],
            fading=FadingConfig(
                profile=FadingProfile.EVA70,
                correlation=CorrelationType.LOW,
            ),
            path_loss_db=80.0,
        )

    @staticmethod
    def scenario_high_speed() -> NetworkScenario:
        """Create high-speed scenario (120 km/h)."""
        return NetworkScenario(
            name="High Speed",
            description="High speed train/vehicle scenario, ETU300 fading",
            cells=[
                CellConfig(
                    cell_id=1,
                    band=1,
                    frequency_mhz=1950.0,
                    power_dbm=-90.0,
                )
            ],
            fading=FadingConfig(
                profile=FadingProfile.ETU300,
                correlation=CorrelationType.LOW,
            ),
            path_loss_db=90.0,
        )

    @staticmethod
    def scenario_urban_macro() -> NetworkScenario:
        """Create urban macro cell scenario."""
        return NetworkScenario(
            name="Urban Macro",
            description="Urban macro cell with interference",
            cells=[
                CellConfig(
                    cell_id=1,
                    band=1,
                    frequency_mhz=1950.0,
                    power_dbm=-85.0,
                ),
            ],
            fading=FadingConfig(
                profile=FadingProfile.ETU70,
                correlation=CorrelationType.MEDIUM,
                awgn_enabled=True,
                awgn_snr_db=20.0,
            ),
            path_loss_db=85.0,
            interference_enabled=True,
            interference_level_dbm=-95.0,
        )

    # =========================================================================
    # Power Ramping / Dynamic Scenarios
    # =========================================================================

    def power_ramp(
        self,
        start_power_dbm: float,
        end_power_dbm: float,
        steps: int = 10,
        step_delay_s: float = 1.0,
        callback=None,
    ) -> List[float]:
        """
        Ramp power level over time.

        Args:
            start_power_dbm: Starting power level
            end_power_dbm: Ending power level
            steps: Number of steps
            step_delay_s: Delay between steps in seconds
            callback: Optional callback function(power, step)

        Returns:
            List of power levels used
        """
        logger.info(f"Power ramp: {start_power_dbm} -> {end_power_dbm} dBm in {steps} steps")

        step_size = (end_power_dbm - start_power_dbm) / (steps - 1)
        power_levels = []

        for i in range(steps):
            power = start_power_dbm + (i * step_size)
            power_levels.append(power)

            self.lte.set_dl_power(rs_epre_dbm=power)

            if callback:
                callback(power, i)

            if i < steps - 1:
                time.sleep(step_delay_s)

        return power_levels

    def snr_sweep(
        self,
        start_snr_db: float,
        end_snr_db: float,
        steps: int = 10,
        step_delay_s: float = 2.0,
        callback=None,
    ) -> List[Tuple[float, any]]:
        """
        Sweep SNR and optionally measure at each point.

        Args:
            start_snr_db: Starting SNR
            end_snr_db: Ending SNR
            steps: Number of steps
            step_delay_s: Delay between steps
            callback: Optional measurement callback(snr) -> result

        Returns:
            List of (snr, result) tuples
        """
        logger.info(f"SNR sweep: {start_snr_db} -> {end_snr_db} dB")

        self.configure_awgn(snr_db=start_snr_db, enabled=True)

        step_size = (end_snr_db - start_snr_db) / (steps - 1)
        results = []

        for i in range(steps):
            snr = start_snr_db + (i * step_size)
            self.configure_awgn(snr_db=snr)
            time.sleep(step_delay_s)

            result = None
            if callback:
                result = callback(snr)

            results.append((snr, result))

        return results

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def reset_to_default(self) -> None:
        """Reset network simulation to default state."""
        logger.info("Resetting network simulation")
        self.disable_fading()
        self.configure_awgn(enabled=False)
        self.set_path_loss(0.0)
        self._current_scenario = None

    def get_status(self) -> Dict[str, any]:
        """Get current simulation status."""
        return {
            "fading_enabled": self._fading_enabled,
            "current_scenario": self._current_scenario.name if self._current_scenario else None,
        }
