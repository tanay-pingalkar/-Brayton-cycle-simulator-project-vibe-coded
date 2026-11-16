"""Constant-cp (cold-air-standard) ideal-gas backend."""

from __future__ import annotations

import math

from brayton_cycle.core.constants import CP_AIR_300K, GAMMA_AIR_300K, P_REF, T_REF
from brayton_cycle.core.interfaces import PropertyProvider


class ConstantCpProvider(PropertyProvider):
    """Calorically perfect ideal gas: cp, cv and gamma are constant.

    The model is defined by (gamma, R), and cp = gamma R / (gamma - 1) follows
    from the Mayer relation. The defaults reproduce [1] Table A-2a for air at
    300 K (cp = 1005 J/(kg K), k = 1.4) by setting
    R = cp (gamma - 1) / gamma = 287.142857 J/(kg K). This is 0.05 % above the
    Table A-1 value R = 287.0 J/(kg K), and it makes the cold-air isentropic
    relation T2/T1 = r_p^((gamma-1)/gamma) exact (REQ-N02).
    ``from_R_gamma`` builds the model from R = 287.0 J/(kg K) instead.

    h(T) = cp (T - T_ref)
    s(T, P) = cp ln(T/T_ref) - R ln(P/P_ref)
    """

    name = "constant-cp"

    def __init__(self, cp: float = CP_AIR_300K, gamma: float = GAMMA_AIR_300K) -> None:
        if cp <= 0.0 or gamma <= 1.0:
            raise ValueError(f"need cp > 0 and gamma > 1, got cp={cp}, gamma={gamma}")
        self._gamma = float(gamma)
        self._R = cp * (gamma - 1.0) / gamma
        self._cp = gamma * self._R / (gamma - 1.0)  # == cp; written as the Mayer form

    @classmethod
    def from_R_gamma(cls, R: float, gamma: float) -> ConstantCpProvider:
        """Build the provider from (R, gamma), with cp = gamma R / (gamma - 1).

        Args:
            R: Specific gas constant [J/(kg K)].
            gamma: Specific-heat ratio cp/cv (> 1).

        Returns:
            New ``ConstantCpProvider``.
        """
        return cls(cp=gamma * R / (gamma - 1.0), gamma=gamma)

    @property
    def R(self) -> float:
        """Specific gas constant [J/(kg K)]. See ``PropertyProvider.R``."""
        return self._R

    def cp(self, T: float) -> float:
        """cp(T) [J/(kg K)]. See ``PropertyProvider.cp``."""
        return self._cp

    def cv(self, T: float) -> float:
        """cv = R / (gamma - 1), computed independently of cp.

        Args:
            T: Temperature [K].

        Returns:
            cv [J/(kg K)].
        """
        return self._R / (self._gamma - 1.0)

    def gamma(self, T: float) -> float:
        """Constant specific-heat ratio. See ``PropertyProvider.gamma``."""
        return self._gamma

    def h(self, T: float) -> float:
        """h(T) [J/kg] relative to T_REF. See ``PropertyProvider.h``."""
        return self._cp * (T - T_REF)

    def s(self, T: float, P: float) -> float:
        """s(T, P) [J/(kg K)]. See ``PropertyProvider.s``."""
        return self._cp * math.log(T / T_REF) - self._R * math.log(P / P_REF)

    def T_from_h(self, h: float) -> float:
        """Inverse of h(T) [K]. See ``PropertyProvider.T_from_h``."""
        T = T_REF + h / self._cp
        if T <= 0.0:
            raise ValueError(f"{self.name}: h = {h:.6g} J/kg gives T <= 0 K")
        return T

    def T_from_s_P(self, s: float, P: float) -> float:
        """Inverse of s(T, P) [K]. See ``PropertyProvider.T_from_s_P``."""
        return T_REF * math.exp((s + self._R * math.log(P / P_REF)) / self._cp)
