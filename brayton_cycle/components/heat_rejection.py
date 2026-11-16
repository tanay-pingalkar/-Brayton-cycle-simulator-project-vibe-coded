"""Heat rejection, station 4 -> 1, which closes the cycle."""

from __future__ import annotations

import math

from brayton_cycle.components._validation import optional_positive, require_positive
from brayton_cycle.core.exceptions import (
    CycleClosureError,
    InputValidationError,
    MassConservationError,
)
from brayton_cycle.core.interfaces import Component, ComponentResult, PropertyProvider
from brayton_cycle.core.state import State

#: Relative tolerance for the closure checks (pressure and mass flow) [-].
CLOSURE_RTOL: float = 1e-9


class HeatRejection(Component):
    """Isobaric heat rejection that returns the fluid to station 1 (T1, P1).

    q_out = h4 - h1           (rejected, > 0; ``ComponentResult.heat`` = -q_out)
    s_gen = (s1 - s4) + q_out / T_sink,   T_sink defaults to T1 (physics §6)

    Closure checks in ``process``:
      * pressure:  P4 == P1 (within CLOSURE_RTOL), otherwise the cycle is not closed;
      * temperature: T4 > T1, so heat really is rejected;
      * mass:      m_dot entering == m_dot at station 1 (air-standard: no fuel mass).

    Args:
        provider: Any ``PropertyProvider`` backend.
        T1, P1: Cycle inlet state [K], [Pa].
        mass_flow: Cycle air mass flow at station 1 [kg/s].
        T_sink: Sink temperature [K]; must satisfy 0 < T_sink <= T1. Defaults to T1.
    """

    def __init__(
        self,
        provider: PropertyProvider,
        T1: float,
        P1: float,
        mass_flow: float = 1.0,
        *,
        T_sink: float | None = None,
        name: str = "heat_rejection",
        outlet_label: str = "1",
    ) -> None:
        super().__init__(provider, name)
        self.T1 = require_positive("T1", T1)
        self.P1 = require_positive("P1", P1)
        self.mass_flow = require_positive("mass_flow", mass_flow)
        self.T_sink = optional_positive("T_sink", T_sink)
        if self.T_sink is not None and self.T_sink > self.T1:
            raise InputValidationError(f"T_sink = {self.T_sink} K must not exceed T1 = {self.T1} K")
        self.outlet_label = outlet_label

    def process(self, inlet: State, mass_flow_in: float | None = None) -> ComponentResult:
        """Cool ``inlet`` (station 4) back to station 1.

        Args:
            inlet: Turbine exit state.
            mass_flow_in: Mass flow arriving from upstream [kg/s]; defaults to
                ``self.mass_flow``. A mismatch raises ``MassConservationError``.
        """
        m_in = self.mass_flow if mass_flow_in is None else mass_flow_in
        if not math.isclose(m_in, self.mass_flow, rel_tol=CLOSURE_RTOL):
            raise MassConservationError(
                f"{self.name}: m_dot in = {m_in:.9g} kg/s but m_dot1 = {self.mass_flow:.9g} kg/s")
        if not math.isclose(inlet.P, self.P1, rel_tol=CLOSURE_RTOL):
            raise CycleClosureError(
                f"{self.name}: P4 = {inlet.P:.9g} Pa differs from P1 = {self.P1:.9g} Pa")
        if inlet.T <= self.T1:
            raise CycleClosureError(
                f"{self.name}: T4 = {inlet.T:.6g} K <= T1 = {self.T1:.6g} K; nothing to reject")
        outlet = self.provider.state(self.T1, self.P1, label=self.outlet_label)
        q_out = inlet.h - outlet.h
        T_sink = self.T_sink if self.T_sink is not None else self.T1
        return ComponentResult(
            component=self.name, inlet=inlet, outlet=outlet, work=0.0, heat=-q_out,
            s_gen=(outlet.s - inlet.s) + q_out / T_sink, mass_flow=m_in,
        )
