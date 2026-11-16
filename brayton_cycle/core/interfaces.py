"""Abstract interfaces: property providers and cycle components.

Sign conventions (used everywhere in the package):
    work  > 0  work delivered BY the fluid to the surroundings (turbine);
    work  < 0  work done ON the fluid (compressor).
    heat  > 0  heat added TO the fluid (combustor);
    heat  < 0  heat rejected by the fluid (heat-rejection process 4->1).
    s_gen >= 0 entropy generated inside the control volume (Second Law).
All quantities are per kg of working fluid (air-standard basis).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from brayton_cycle.core.constants import S_GEN_TOL
from brayton_cycle.core.exceptions import SecondLawViolation
from brayton_cycle.core.state import State

__all__ = ["Component", "ComponentResult", "PropertyProvider", "SecondLawViolation"]


class PropertyProvider(ABC):
    """Ideal-gas property backend (constant-cp, variable-cp, CoolProp, Cantera).

    All methods use SI units: T [K], P [Pa], h [J/kg], s [J/(kg*K)].
    Implementations must use the reference state (``T_REF``, ``P_REF``) from
    ``brayton_cycle.core.constants`` so that backends are interchangeable.
    """

    #: Human-readable backend name, e.g. ``"constant-cp"``.
    name: str = "abstract"

    @property
    @abstractmethod
    def R(self) -> float:
        """Specific gas constant [J/(kg*K)]."""

    @abstractmethod
    def cp(self, T: float) -> float:
        """Constant-pressure specific heat at temperature T [J/(kg*K)].

        Args:
            T: Temperature [K].

        Returns:
            cp [J/(kg K)].
        """

    @abstractmethod
    def h(self, T: float) -> float:
        """Specific enthalpy h(T) [J/kg] (ideal gas: independent of P).

        Args:
            T: Temperature [K].

        Returns:
            h [J/kg] relative to T_REF.
        """

    @abstractmethod
    def s(self, T: float, P: float) -> float:
        """Specific entropy s(T, P) = s_deg(T) - R ln(P/P_ref) [J/(kg*K)].

        Args:
            T: Temperature [K].
            P: Pressure [Pa].

        Returns:
            s [J/(kg K)] relative to (T_REF, P_REF).
        """

    @abstractmethod
    def T_from_h(self, h: float) -> float:
        """Invert h(T): temperature [K] for a given enthalpy [J/kg].

        Args:
            h: Specific enthalpy [J/kg].

        Returns:
            Temperature [K].
        """

    @abstractmethod
    def T_from_s_P(self, s: float, P: float) -> float:
        """Invert s(T, P): temperature [K] for given entropy and pressure.

        Args:
            s: Specific entropy [J/(kg K)].
            P: Pressure [Pa].

        Returns:
            Temperature [K].
        """

    # ---- concrete helpers (may be overridden for efficiency) --------------
    def cv(self, T: float) -> float:
        """Constant-volume specific heat cv = cp - R [J/(kg*K)].

        Args:
            T: Temperature [K].

        Returns:
            cv [J/(kg K)].
        """
        return self.cp(T) - self.R

    def gamma(self, T: float) -> float:
        """Specific-heat ratio cp/cv [-].

        Args:
            T: Temperature [K].

        Returns:
            cp/cv [-].
        """
        return self.cp(T) / self.cv(T)

    def v(self, T: float, P: float) -> float:
        """Specific volume [m^3/kg] from the ideal-gas law v = R T / P.

        Args:
            T: Temperature [K].
            P: Pressure [Pa].

        Returns:
            Specific volume [m^3/kg].
        """
        return self.R * T / P

    def state(self, T: float, P: float, label: str = "") -> State:
        """Build a fully consistent ``State`` from (T, P).

        Args:
            T: Temperature [K].
            P: Pressure [Pa].
            label: Station label for the returned state.

        Returns:
            Consistent ``State``.
        """
        return State(T=T, P=P, h=self.h(T), s=self.s(T, P), label=label)

    def state_from_h_P(self, h: float, P: float, label: str = "") -> State:
        """Build a ``State`` from (h, P).

        Args:
            h: Specific enthalpy [J/kg].
            P: Pressure [Pa].
            label: Station label for the returned state.

        Returns:
            Consistent ``State``.
        """
        return self.state(self.T_from_h(h), P, label)

    def state_from_s_P(self, s: float, P: float, label: str = "") -> State:
        """Build a ``State`` from (s, P) - used for isentropic end states.

        Args:
            s: Specific entropy [J/(kg K)].
            P: Pressure [Pa].
            label: Station label for the returned state.

        Returns:
            Consistent ``State``.
        """
        return self.state(self.T_from_s_P(s, P), P, label)


@dataclass(frozen=True, slots=True)
class ComponentResult:
    """Outcome of one steady-flow component process.

    Attributes:
        component: Name of the component that produced the result.
        inlet: Inlet state.
        outlet: Outlet state.
        work: Specific work [J/kg]; sign convention in module docstring.
        heat: Specific heat [J/kg]; sign convention in module docstring.
        s_gen: Specific entropy generation [J/(kg*K)], must be >= 0.
        fuel_air_ratio: Fuel-air ratio f [-] (combustor only, else ``None``).
        isentropic_outlet: Ideal end state (compressor/turbine only).
        mass_flow: Air mass flow through the component [kg/s] (default 1.0,
            so ``power`` equals specific work on a per-kg basis).
    """

    component: str
    inlet: State
    outlet: State
    work: float
    heat: float
    s_gen: float
    fuel_air_ratio: float | None = None
    isentropic_outlet: State | None = None
    mass_flow: float = 1.0

    def __post_init__(self) -> None:
        if not (math.isfinite(self.mass_flow) and self.mass_flow > 0.0):
            raise ValueError(f"ComponentResult.mass_flow must be > 0, got {self.mass_flow!r}")
        for name in ("work", "heat", "s_gen"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"ComponentResult.{name} must be finite")
        if self.s_gen < -S_GEN_TOL:
            raise SecondLawViolation(
                f"{self.component}: s_gen = {self.s_gen:.3e} J/(kg*K) < 0"
            )

    @property
    def power(self) -> float:
        """Shaft power m_dot * work [W]; > 0 delivered by the fluid (turbine)."""
        return self.mass_flow * self.work

    @property
    def heat_rate(self) -> float:
        """Heat-transfer rate m_dot * heat [W]; > 0 added to the fluid."""
        return self.mass_flow * self.heat

    @property
    def entropy_generation_rate(self) -> float:
        """m_dot * s_gen [W/K]."""
        return self.mass_flow * self.s_gen

    @property
    def energy_residual(self) -> float:
        """SFEE residual (h_out - h_in) - (heat - work) [J/kg]; should be ~0."""
        return (self.outlet.h - self.inlet.h) - (self.heat - self.work)


class Component(ABC):
    """A steady-flow control volume acting on an inlet ``State``.

    Concrete components receive their ``PropertyProvider`` and parameters at
    construction and must be stateless with respect to ``process`` calls.
    """

    def __init__(self, provider: PropertyProvider, name: str) -> None:
        self.provider = provider
        self.name = name

    @abstractmethod
    def process(self, inlet: State) -> ComponentResult:
        """Apply the component's process to ``inlet`` and return the result.

        Args:
            inlet: Inlet state of the control volume.

        Returns:
            ``ComponentResult`` with outlet state, work, heat and s_gen.
        """
