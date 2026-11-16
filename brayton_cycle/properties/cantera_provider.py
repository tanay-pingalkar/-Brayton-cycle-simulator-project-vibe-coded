"""Optional Cantera adapter: ideal-gas air mixture from NASA polynomials [4][5].

Air is a frozen mixture of N2, O2 and Ar with mole fractions 0.7812, 0.2096
and 0.0092. This is the composition that defines "air" in Lemmon et al. [2],
so the adapter and the CoolProp adapter model the same fluid. Species data come
from Cantera's bundled ``air.yaml`` (NASA 7-coefficient polynomials [5]). The
composition is held fixed (no equilibrium or dissociation). Values are shifted
so that h = 0 at T_REF and s = 0 at (T_REF, P_REF). Install with
``pip install -e .[cantera]``. Record the installed version's Zenodo DOI in
docs/references.md [4].
"""

from __future__ import annotations

from brayton_cycle.core.constants import P_REF, T_REF
from brayton_cycle.core.interfaces import PropertyProvider
from brayton_cycle.properties._common import BackendUnavailable, invert_monotonic

#: Dry-air composition (mole fractions) that defines air in [2].
AIR_COMPOSITION: str = "N2:0.7812, O2:0.2096, AR:0.0092"


class CanteraProvider(PropertyProvider):
    """Air properties from a frozen Cantera ideal-gas mixture [4][5]."""

    name = "cantera"

    def __init__(self, mechanism: str = "air.yaml", composition: str = AIR_COMPOSITION) -> None:
        try:
            import cantera as ct  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise BackendUnavailable(
                "Cantera backend requested but the 'cantera' package is not installed. "
                "Install it with: pip install -e \".[cantera]\"  (or pip install cantera)"
            ) from exc
        self._gas = ct.Solution(mechanism)
        self._X = composition
        self._gas.TPX = T_REF, P_REF, composition
        self._R = ct.gas_constant / self._gas.mean_molecular_weight  # J/(kmol K) / (kg/kmol)
        self._h0 = self._gas.enthalpy_mass
        self._s0 = self._gas.entropy_mass
        self.T_min = float(self._gas.min_temp)
        self.T_max = float(self._gas.max_temp)

    def _set(self, T: float, P: float = P_REF) -> None:
        if not self.T_min <= T <= self.T_max:
            raise ValueError(f"{self.name}: T = {T:.6g} K outside NASA-polynomial range "
                             f"[{self.T_min:g}, {self.T_max:g}] K [5]")
        self._gas.TPX = T, P, self._X

    @property
    def R(self) -> float:
        """Specific gas constant [J/(kg K)]. See ``PropertyProvider.R``."""
        return self._R

    def cp(self, T: float) -> float:
        """cp(T) [J/(kg K)]. See ``PropertyProvider.cp``."""
        self._set(T)
        return self._gas.cp_mass

    def h(self, T: float) -> float:
        """h(T) [J/kg] relative to T_REF. See ``PropertyProvider.h``."""
        self._set(T)
        return self._gas.enthalpy_mass - self._h0

    def s(self, T: float, P: float) -> float:
        """s(T, P) [J/(kg K)]. See ``PropertyProvider.s``."""
        self._set(T, P)
        return self._gas.entropy_mass - self._s0

    def T_from_h(self, h: float) -> float:
        """Inverse of h(T) [K]. See ``PropertyProvider.T_from_h``."""
        return invert_monotonic(self.h, h, self.T_min, self.T_max, "h [J/kg]", self.name)

    def T_from_s_P(self, s: float, P: float) -> float:
        """Inverse of s(T, P) [K]. See ``PropertyProvider.T_from_s_P``."""
        return invert_monotonic(lambda T: self.s(T, P), s, self.T_min, self.T_max,
                                "s [J/(kg K)]", self.name)
