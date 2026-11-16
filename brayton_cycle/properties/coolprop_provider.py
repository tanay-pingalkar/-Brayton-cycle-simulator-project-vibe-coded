"""Optional CoolProp adapter: pseudo-pure air, Lemmon et al. (2000) EOS [2], via CoolProp [3].

The adapter is an ideal-gas projection, consistent with the air-standard cycle.
h(T) and cp(T) are evaluated at P_ref, where air at T >= 273 K is ideal to
better than 0.1 %. s(T, P) = s(T, P_ref) - R ln(P/P_ref). Values are shifted
so that h = 0 at T_REF and s = 0 at (T_REF, P_REF), matching the other
backends. Validity: 60-2000 K [2]. Install with ``pip install -e .[coolprop]``.
"""

from __future__ import annotations

import math

from brayton_cycle.core.constants import P_REF, T_REF
from brayton_cycle.core.interfaces import PropertyProvider
from brayton_cycle.properties._common import BackendUnavailable, invert_monotonic


class CoolPropProvider(PropertyProvider):
    """Air properties from CoolProp's ``"Air"`` pseudo-pure fluid [2][3]."""

    name = "coolprop"
    T_min: float = 60.0    # [2] title range
    T_max: float = 2000.0  # [2]

    def __init__(self, fluid: str = "Air") -> None:
        try:
            from CoolProp.CoolProp import PropsSI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise BackendUnavailable(
                "CoolProp backend requested but the 'CoolProp' package is not installed. "
                "Install it with: pip install -e \".[coolprop]\"  (or pip install CoolProp)"
            ) from exc
        self._props = PropsSI
        self._fluid = fluid
        self._R = PropsSI("GAS_CONSTANT", fluid) / PropsSI("M", fluid)
        self._h0 = PropsSI("Hmass", "T", T_REF, "P", P_REF, fluid)
        self._s0 = PropsSI("Smass", "T", T_REF, "P", P_REF, fluid)

    def _check(self, T: float) -> None:
        if not self.T_min <= T <= self.T_max:
            raise ValueError(f"{self.name}: T = {T:.6g} K outside [{self.T_min}, {self.T_max}] K [2]")

    @property
    def R(self) -> float:
        """Specific gas constant [J/(kg K)]. See ``PropertyProvider.R``."""
        return self._R

    def cp(self, T: float) -> float:
        """cp(T) [J/(kg K)]. See ``PropertyProvider.cp``."""
        self._check(T)
        return self._props("Cpmass", "T", T, "P", P_REF, self._fluid)

    def h(self, T: float) -> float:
        """h(T) [J/kg] relative to T_REF. See ``PropertyProvider.h``."""
        self._check(T)
        return self._props("Hmass", "T", T, "P", P_REF, self._fluid) - self._h0

    def s(self, T: float, P: float) -> float:
        """s(T, P) [J/(kg K)]. See ``PropertyProvider.s``."""
        self._check(T)
        s_ref_p = self._props("Smass", "T", T, "P", P_REF, self._fluid) - self._s0
        return s_ref_p - self._R * math.log(P / P_REF)

    def T_from_h(self, h: float) -> float:
        """Inverse of h(T) [K]. See ``PropertyProvider.T_from_h``."""
        return invert_monotonic(self.h, h, self.T_min, self.T_max, "h [J/kg]", self.name)

    def T_from_s_P(self, s: float, P: float) -> float:
        """Inverse of s(T, P) [K]. See ``PropertyProvider.T_from_s_P``."""
        return invert_monotonic(lambda T: self.s(T, P), s, self.T_min, self.T_max,
                                "s [J/(kg K)]", self.name)
