"""Variable-cp ideal-gas air backend: Cengel Table A-2c polynomial [1].

    cp_bar(T) = a + b T + c T^2 + d T^3    [kJ/(kmol K) == J/(mol K)], T in K

The coefficients are used exactly as published, with T in kelvin. h(T) and
s_deg(T) are the closed-form integrals of cp_bar and cp_bar/T from T_REF; no
numerical quadrature is used:

    h_bar(T)  = a dT + b/2 d(T^2) + c/3 d(T^3) + d/4 d(T^4)
    s0_bar(T) = a ln(T/T_ref) + b dT + c/2 d(T^2) + d/3 d(T^3)

where d(X) = X(T) - X(T_REF). Mass-specific values divide by M_AIR, and
s(T, P) = s0(T) - R ln(P/P_ref) with R = R_AIR [1] Table A-1.

Validity: 273-1800 K, max error 0.72 % [1] Table A-2c. Outside this range the
provider raises ``ValueError`` by default. With ``extrapolate=True`` it issues
a ``PropertyRangeWarning`` instead, and the inversion bracket widens to
EXTRAPOLATION_BRACKET.
"""

from __future__ import annotations

import math
import warnings

from brayton_cycle.core.constants import (
    CP_POLY_AIR_A as _A,
    CP_POLY_AIR_B as _B,
    CP_POLY_AIR_C as _C,
    CP_POLY_AIR_D as _D,
    CP_POLY_AIR_T_MAX,
    CP_POLY_AIR_T_MIN,
    M_AIR,
    P_REF,
    R_AIR,
    T_REF,
)
from brayton_cycle.core.interfaces import PropertyProvider
from brayton_cycle.properties._common import PropertyRangeWarning, invert_monotonic

#: Bracket [K] used by the inverse functions when ``extrapolate=True``. Below
#: about 100 K the cubic is meaningless, and above 3000 K dissociation dominates.
EXTRAPOLATION_BRACKET: tuple[float, float] = (100.0, 3000.0)


def _h_bar(T: float) -> float:
    """Molar enthalpy relative to T_REF [J/mol] (Horner form of the integral)."""
    return T * (_A + T * (_B / 2 + T * (_C / 3 + T * _D / 4)))


def _s0_bar(T: float) -> float:
    """Molar s_deg without the T_REF offset [J/(mol K)]."""
    return _A * math.log(T) + T * (_B + T * (_C / 2 + T * _D / 3))


_H_BAR_REF = _h_bar(T_REF)
_S0_BAR_REF = _s0_bar(T_REF)


class VariableCpProvider(PropertyProvider):
    """Thermally perfect air using the Table A-2c cubic cp(T) [1]."""

    name = "variable-cp"
    T_min: float = CP_POLY_AIR_T_MIN
    T_max: float = CP_POLY_AIR_T_MAX

    def __init__(self, extrapolate: bool = False) -> None:
        self.extrapolate = extrapolate

    # ---- range policy -----------------------------------------------------
    def _check(self, T: float) -> None:
        if self.T_min <= T <= self.T_max:
            return
        msg = (f"{self.name}: T = {T:.6g} K is outside the Table A-2c validity range "
               f"[{self.T_min:g}, {self.T_max:g}] K ([1], max error 0.72 % inside)")
        if not self.extrapolate:
            raise ValueError(msg + "; pass extrapolate=True to allow with a warning")
        warnings.warn(msg, PropertyRangeWarning, stacklevel=3)

    @property
    def _bracket(self) -> tuple[float, float]:
        return EXTRAPOLATION_BRACKET if self.extrapolate else (self.T_min, self.T_max)

    # ---- ABC --------------------------------------------------------------
    @property
    def R(self) -> float:
        """Specific gas constant [J/(kg K)]. See ``PropertyProvider.R``."""
        return R_AIR

    def cp(self, T: float) -> float:
        """cp(T) [J/(kg K)]. See ``PropertyProvider.cp``."""
        self._check(T)
        return (_A + T * (_B + T * (_C + T * _D))) / M_AIR

    def h(self, T: float) -> float:
        """h(T) [J/kg] relative to T_REF. See ``PropertyProvider.h``."""
        self._check(T)
        return (_h_bar(T) - _H_BAR_REF) / M_AIR

    def s0(self, T: float) -> float:
        """Standard-state entropy s_deg(T) at P_ref [J/(kg K)].

        Args:
            T: Temperature [K].

        Returns:
            s0(T) [J/(kg K)].
        """
        self._check(T)
        return (_s0_bar(T) - _S0_BAR_REF) / M_AIR

    def s(self, T: float, P: float) -> float:
        """s(T, P) [J/(kg K)]. See ``PropertyProvider.s``."""
        return self.s0(T) - R_AIR * math.log(P / P_REF)

    def T_from_h(self, h: float) -> float:
        """Inverse of h(T) [K]. See ``PropertyProvider.T_from_h``."""
        lo, hi = self._bracket
        f = lambda T: (_h_bar(T) - _H_BAR_REF) / M_AIR  # noqa: E731  (no range check inside solver)
        T = invert_monotonic(f, h, lo, hi, "h [J/kg]", self.name)
        self._check(T)
        return T

    def T_from_s_P(self, s: float, P: float) -> float:
        """Inverse of s(T, P) [K]. See ``PropertyProvider.T_from_s_P``."""
        lo, hi = self._bracket
        s0_target = s + R_AIR * math.log(P / P_REF)
        f = lambda T: (_s0_bar(T) - _S0_BAR_REF) / M_AIR  # noqa: E731
        T = invert_monotonic(f, s0_target, lo, hi, "s0 [J/(kg K)]", self.name)
        self._check(T)
        return T
