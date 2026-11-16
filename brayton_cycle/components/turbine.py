"""Adiabatic turbine, station 3 -> 4."""

from __future__ import annotations

from brayton_cycle.components._turbomachine import adiabatic_process
from brayton_cycle.components._validation import require_efficiency, require_positive
from brayton_cycle.core.exceptions import InvalidPressureRatioError
from brayton_cycle.core.interfaces import Component, ComponentResult, PropertyProvider
from brayton_cycle.core.state import State


class Turbine(Component):
    """Steady-flow adiabatic turbine expanding to a fixed outlet pressure.

    s(T4s, P4) = s3
    w_t = eta_t (h3 - h4s)        (output work, > 0)
    h4 = h3 - w_t
    W_dot_t = m_dot w_t
    s_gen,t = s4 - s3

    In the 4-station cycle the outlet pressure is P1 (no exhaust loss), so the
    expansion ratio P3/P4 = r_p (1 - dP_comb) is set by the upstream components.

    Args:
        provider: Any ``PropertyProvider`` backend.
        outlet_pressure: P4 [Pa], > 0. Must be below the inlet pressure at run time.
        eta_t: Isentropic efficiency, 0 < eta_t <= 1.
        mass_flow: Gas mass flow [kg/s], > 0 (air-standard: equal to the air flow).
        outlet_label: Station label of the outlet.

    Raises:
        InvalidEfficiencyError, InputValidationError (constructor);
        InvalidPressureRatioError if P_inlet <= outlet_pressure (``process``).
    """

    def __init__(
        self,
        provider: PropertyProvider,
        outlet_pressure: float,
        eta_t: float,
        mass_flow: float = 1.0,
        *,
        name: str = "turbine",
        outlet_label: str = "4",
    ) -> None:
        super().__init__(provider, name)
        self.outlet_pressure = require_positive("outlet_pressure", outlet_pressure,
                                                InvalidPressureRatioError)
        self.eta_t = require_efficiency("eta_t", eta_t)
        self.mass_flow = require_positive("mass_flow", mass_flow)
        self.outlet_label = outlet_label

    def process(self, inlet: State) -> ComponentResult:
        """Expand ``inlet`` to ``outlet_pressure``.

        Args:
            inlet: Inlet state of the control volume.

        Returns:
            ``ComponentResult`` for station 4 (``work`` > 0).
        """
        if inlet.P <= self.outlet_pressure:
            raise InvalidPressureRatioError(
                f"{self.name}: inlet pressure {inlet.P:.6g} Pa must exceed outlet "
                f"pressure {self.outlet_pressure:.6g} Pa (expansion ratio must be > 1)"
            )
        return adiabatic_process(
            self.provider,
            inlet,
            self.outlet_pressure,
            self.eta_t,
            compression=False,
            name=self.name,
            outlet_label=self.outlet_label,
            mass_flow=self.mass_flow,
        )
