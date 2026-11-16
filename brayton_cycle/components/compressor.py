"""Adiabatic compressor, station 1 -> 2."""

from __future__ import annotations

from brayton_cycle.components._turbomachine import adiabatic_process
from brayton_cycle.components._validation import (
    require_efficiency,
    require_positive,
    require_pressure_ratio,
)
from brayton_cycle.core.interfaces import Component, ComponentResult, PropertyProvider
from brayton_cycle.core.state import State


class Compressor(Component):
    """Steady-flow adiabatic compressor.

    P2 = r_p P1
    s(T2s, P2) = s1
    w_c = (h2s - h1) / eta_c       (input work, > 0)
    h2 = h1 + w_c
    W_dot_c = m_dot w_c
    s_gen,c = s2 - s1

    The returned ``ComponentResult.work`` follows the package sign convention
    (work by the fluid), so it equals -w_c. Use ``compressor_work`` for w_c.

    Args:
        provider: Any ``PropertyProvider`` backend.
        pressure_ratio: r_p = P2/P1 [-], must be > 1.
        eta_c: Isentropic efficiency, 0 < eta_c <= 1.
        mass_flow: Air mass flow [kg/s], > 0 (default 1 kg/s, per-kg results).
        outlet_label: Station label of the outlet (isentropic state gets "<label>s").

    Raises:
        InvalidPressureRatioError, InvalidEfficiencyError, InputValidationError.
    """

    def __init__(
        self,
        provider: PropertyProvider,
        pressure_ratio: float,
        eta_c: float,
        mass_flow: float = 1.0,
        *,
        name: str = "compressor",
        outlet_label: str = "2",
    ) -> None:
        super().__init__(provider, name)
        self.pressure_ratio = require_pressure_ratio("pressure_ratio", pressure_ratio)
        self.eta_c = require_efficiency("eta_c", eta_c)
        self.mass_flow = require_positive("mass_flow", mass_flow)
        self.outlet_label = outlet_label

    def process(self, inlet: State) -> ComponentResult:
        """Compress ``inlet`` to P2 = r_p P1.

        Args:
            inlet: Inlet state of the control volume.

        Returns:
            ``ComponentResult`` for station 2 (``work`` < 0 by convention).
        """
        return adiabatic_process(
            self.provider,
            inlet,
            inlet.P * self.pressure_ratio,
            self.eta_c,
            compression=True,
            name=self.name,
            outlet_label=self.outlet_label,
            mass_flow=self.mass_flow,
        )

    @staticmethod
    def compressor_work(result: ComponentResult) -> float:
        """Specific input work w_c = h2 - h1 [J/kg] (positive).

        Args:
            result: Result returned by this component's ``process``.

        Returns:
            w_c [J/kg], positive.
        """
        return -result.work

    @staticmethod
    def compressor_power(result: ComponentResult) -> float:
        """Input power W_dot_c = m_dot w_c [W] (positive).

        Args:
            result: Result returned by this component's ``process``.

        Returns:
            W_dot_c [W], positive.
        """
        return -result.power
