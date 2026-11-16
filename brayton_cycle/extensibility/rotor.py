"""Rotor-sizing hook (REQ-E01).

The stub sizes one annulus with a mean-line continuity estimate, the usual
first step in [7]:

    rho = P / (R T)                          ideal gas (static state assumed)
    A   = m_dot / (rho C_a)                  continuity
    A   = pi (r_t^2 - r_h^2),  r_h = nu r_t  annulus with hub-tip ratio nu
    N   = U_m / (2 pi r_m) * 60              shaft speed from the mean blade speed

The defaults for C_a, nu and U_m are ILLUSTRATIVE PLACEHOLDERS
[FLAG: no specific source; take them from [7] or project data for real sizing].
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from brayton_cycle.core.exceptions import InputValidationError
from brayton_cycle.core.state import State


@dataclass(frozen=True, slots=True)
class RotorSizingResult:
    """Typed result of a rotor-sizing estimate (SI units).

    Attributes:
        annulus_area: Flow annulus area [m^2].
        hub_radius, tip_radius, mean_radius: Radii [m]; mean = (hub + tip) / 2.
        blade_height: tip - hub [m].
        rotational_speed_rpm: Shaft speed [rev/min].
        density: Gas density used [kg/m^3].
        illustrative: True while placeholder inputs are used.
        method: Name of the sizing method.
    """

    annulus_area: float
    hub_radius: float
    tip_radius: float
    mean_radius: float
    blade_height: float
    rotational_speed_rpm: float
    density: float
    illustrative: bool
    method: str


class RotorSizing(ABC):
    """Strategy interface: size a rotor row for a given flow and state."""

    name: str = "abstract"

    @abstractmethod
    def size(self, mass_flow: float, state: State, gas_constant: float) -> RotorSizingResult:
        """Size a row passing ``mass_flow`` [kg/s] at ``state``; R in J/(kg K).

        Args:
            mass_flow: Mass flow [kg/s].
            state: Gas state at the rotor row.
            gas_constant: Specific gas constant R [J/(kg K)].

        Returns:
            ``RotorSizingResult``.
        """


class MeanLineRotorSizingStub(RotorSizing):
    """Single-annulus continuity sizing with placeholder design choices."""

    name = "mean-line continuity stub (illustrative)"

    def __init__(self, axial_velocity: float = 150.0, hub_tip_ratio: float = 0.6,
                 mean_blade_speed: float = 350.0) -> None:
        if axial_velocity <= 0.0 or mean_blade_speed <= 0.0:
            raise InputValidationError("axial_velocity and mean_blade_speed must be > 0")
        if not 0.0 < hub_tip_ratio < 1.0:
            raise InputValidationError("hub_tip_ratio must be in (0, 1)")
        self.axial_velocity = axial_velocity
        self.hub_tip_ratio = hub_tip_ratio
        self.mean_blade_speed = mean_blade_speed

    def size(self, mass_flow: float, state: State, gas_constant: float) -> RotorSizingResult:
        """Continuity sizing of one annulus. See ``RotorSizing.size``."""
        if mass_flow <= 0.0 or gas_constant <= 0.0:
            raise InputValidationError("mass_flow and gas_constant must be > 0")
        rho = state.P / (gas_constant * state.T)
        area = mass_flow / (rho * self.axial_velocity)
        r_tip = math.sqrt(area / (math.pi * (1.0 - self.hub_tip_ratio**2)))
        r_hub = self.hub_tip_ratio * r_tip
        r_mean = 0.5 * (r_hub + r_tip)
        rpm = self.mean_blade_speed / (2.0 * math.pi * r_mean) * 60.0
        return RotorSizingResult(annulus_area=area, hub_radius=r_hub, tip_radius=r_tip,
                                 mean_radius=r_mean, blade_height=r_tip - r_hub,
                                 rotational_speed_rpm=rpm, density=rho,
                                 illustrative=True, method=self.name)
