"""Combustor, station 2 -> 3, in target-T3 or fuel-air-ratio mode (REQ-F02).

Air-standard limitation: the working fluid stays air with unchanged composition
and mass flow. Fuel only supplies heat, q_in = eta_comb f LHV. Fuel mass
addition, combustion-product properties and dissociation are not modelled.
The results are therefore the air-standard idealisation (error grows with f;
see docs/physics_formulation.md, Section 1).
"""

from __future__ import annotations

from enum import Enum

from brayton_cycle.components._validation import (optional_positive, require_efficiency,
                                                  require_positive, require_pressure_loss)
from brayton_cycle.core.constants import FAR_STOICH_KEROSENE
from brayton_cycle.core.exceptions import (CombustorTemperatureError, FuelAirRatioError,
                                           InputValidationError)
from brayton_cycle.core.interfaces import Component, ComponentResult, PropertyProvider
from brayton_cycle.core.state import State


class CombustorMode(str, Enum):
    """How the combustor heat addition is specified."""

    TARGET_T3 = "target_T3"            # (a) T3 given, f computed
    FUEL_AIR_RATIO = "fuel_air_ratio"  # (b) f given, T3 computed


class Combustor(Component):
    """Constant-composition heat addition with a fractional pressure loss.

    P3 = P2 (1 - dP_comb)
    q_in = h3 - h2 = eta_comb f LHV
    (a) f = (h3 - h2) / (eta_comb LHV)
    (b) h3 = h2 + eta_comb f LHV, then T3 = T(h3)
    s_gen = (s3 - s2) - q_in / T_source,  T_source defaults to T3 (physics §6)

    Raises:
        InputValidationError and subclasses for invalid arguments;
        CombustorTemperatureError if T3 <= T2 (mode a);
        FuelAirRatioError if f is outside (0, max_fuel_air_ratio].
    """

    def __init__(
        self,
        provider: PropertyProvider,
        mode: CombustorMode | str,
        *,
        T3: float | None = None,
        fuel_air_ratio: float | None = None,
        eta_comb: float,
        dp_comb: float,
        lhv: float,
        mass_flow: float = 1.0,
        T_source: float | None = None,
        max_fuel_air_ratio: float = FAR_STOICH_KEROSENE,
        name: str = "combustor",
        outlet_label: str = "3",
    ) -> None:
        super().__init__(provider, name)
        try:
            self.mode = CombustorMode(mode)
        except ValueError:
            raise InputValidationError(f"unknown combustor mode {mode!r}; "
                                       f"use one of {[m.value for m in CombustorMode]}") from None
        self.eta_comb = require_efficiency("eta_comb", eta_comb)
        self.dp_comb = require_pressure_loss("dp_comb", dp_comb)
        self.lhv = require_positive("lhv", lhv)
        self.mass_flow = require_positive("mass_flow", mass_flow)
        self.T_source = optional_positive("T_source", T_source)
        self.max_fuel_air_ratio = require_positive("max_fuel_air_ratio", max_fuel_air_ratio,
                                                   FuelAirRatioError)
        self.outlet_label = outlet_label
        if self.mode is CombustorMode.TARGET_T3:
            if T3 is None or fuel_air_ratio is not None:
                raise InputValidationError("mode 'target_T3' needs T3 and no fuel_air_ratio")
            self.T3: float | None = require_positive("T3", T3)
            self.fuel_air_ratio: float | None = None
        else:
            if fuel_air_ratio is None or T3 is not None:
                raise InputValidationError("mode 'fuel_air_ratio' needs fuel_air_ratio and no T3")
            self.fuel_air_ratio = self._check_far(
                require_positive("fuel_air_ratio", fuel_air_ratio, FuelAirRatioError))
            self.T3 = None

    def _check_far(self, f: float) -> float:
        if not 0.0 < f <= self.max_fuel_air_ratio:
            raise FuelAirRatioError(f"{self.name}: f = {f:.5g} outside physical range "
                                    f"(0, {self.max_fuel_air_ratio:g}] (stoichiometric limit)")
        return f

    def process(self, inlet: State) -> ComponentResult:
        """Add heat to ``inlet`` (station 2) and return station 3.

        Args:
            inlet: Inlet state of the control volume.

        Returns:
            ``ComponentResult`` for station 3 including the fuel-air ratio.
        """
        P3 = inlet.P * (1.0 - self.dp_comb)
        if self.T3 is not None:  # mode (a): target T3
            if self.T3 <= inlet.T:
                raise CombustorTemperatureError(
                    f"{self.name}: target T3 = {self.T3:.6g} K must exceed T2 = {inlet.T:.6g} K")
            outlet = self.provider.state(self.T3, P3, label=self.outlet_label)
            f = self._check_far((outlet.h - inlet.h) / (self.eta_comb * self.lhv))
        else:  # mode (b): given f (set and validated in __init__)
            f = float(self.fuel_air_ratio)  # type: ignore[arg-type]
            h3 = inlet.h + self.eta_comb * f * self.lhv
            outlet = self.provider.state_from_h_P(h3, P3, label=self.outlet_label)
        q_in = outlet.h - inlet.h
        T_source = self.T_source if self.T_source is not None else outlet.T
        if T_source < outlet.T:
            raise InputValidationError(f"{self.name}: T_source = {T_source:.6g} K is below "
                                       f"T3 = {outlet.T:.6g} K; heat cannot flow up-gradient")
        return ComponentResult(
            component=self.name, inlet=inlet, outlet=outlet, work=0.0, heat=q_in,
            s_gen=(outlet.s - inlet.s) - q_in / T_source,
            fuel_air_ratio=f, mass_flow=self.mass_flow,
        )

    def fuel_flow(self, result: ComponentResult) -> float:
        """Fuel mass flow m_dot_f = m_dot f [kg/s].

        Args:
            result: Result returned by this component's ``process``.

        Returns:
            Fuel mass flow [kg/s].
        """
        return result.mass_flow * float(result.fuel_air_ratio)  # type: ignore[arg-type]
