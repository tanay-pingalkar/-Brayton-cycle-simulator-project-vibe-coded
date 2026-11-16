"""Exercise the CoolProp/Cantera adapter code paths without the real packages.

Small fake ``CoolProp`` and ``cantera`` modules are injected into
``sys.modules``. They return Table A-2c ideal-gas air shifted by an arbitrary
datum, which checks that the adapters re-reference h and s, derive R from the
library constants, invert correctly, and enforce their temperature range. The
physics of the real libraries is checked by the importorskip cross-checks in
test_properties.py.
"""

from __future__ import annotations

import sys
import types

import pytest

from brayton_cycle.core.constants import P_REF
from brayton_cycle.properties import VariableCpProvider, get_property_provider

# Extrapolating: the CoolProp adapter brackets inversions over 60-2000 K [2].
_VC = VariableCpProvider(extrapolate=True)
pytestmark = pytest.mark.filterwarnings("ignore::brayton_cycle.properties.PropertyRangeWarning")
H_OFFSET, S_OFFSET = 4.2e5, 3.9e3  # arbitrary foreign datum


def _fake_coolprop() -> types.ModuleType:
    def PropsSI(out: str, *args: object) -> float:  # noqa: N802 - mimic CoolProp
        if out == "GAS_CONSTANT":
            return 8.314462618
        if out == "M":
            return 28.97e-3
        _, T, _, P, _fluid = args
        T, P = float(T), float(P)  # type: ignore[arg-type]
        return {"Hmass": _VC.h(T) + H_OFFSET,
                "Smass": _VC.s(T, P) + S_OFFSET,
                "Cpmass": _VC.cp(T)}[out]

    pkg = types.ModuleType("CoolProp")
    sub = types.ModuleType("CoolProp.CoolProp")
    sub.PropsSI = PropsSI  # type: ignore[attr-defined]
    pkg.CoolProp = sub  # type: ignore[attr-defined]
    return pkg


def _fake_cantera() -> types.ModuleType:
    class Solution:
        mean_molecular_weight = 28.97
        min_temp, max_temp = 273.0, 1800.0

        def __init__(self, mech: str) -> None:
            self.T, self.P = 300.0, P_REF

        @property
        def TPX(self) -> tuple[float, float, str]:
            return self.T, self.P, ""

        @TPX.setter
        def TPX(self, v: tuple[float, float, str]) -> None:
            self.T, self.P = float(v[0]), float(v[1])

        enthalpy_mass = property(lambda self: _VC.h(self.T) + H_OFFSET)
        entropy_mass = property(lambda self: _VC.s(self.T, self.P) + S_OFFSET)
        cp_mass = property(lambda self: _VC.cp(self.T))

    mod = types.ModuleType("cantera")
    mod.Solution = Solution  # type: ignore[attr-defined]
    mod.gas_constant = 8314.462618  # type: ignore[attr-defined]
    return mod


@pytest.fixture(params=["coolprop", "cantera"])
def adapter(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    if request.param == "coolprop":
        fake = _fake_coolprop()
        monkeypatch.setitem(sys.modules, "CoolProp", fake)
        monkeypatch.setitem(sys.modules, "CoolProp.CoolProp", fake.CoolProp)
    else:
        monkeypatch.setitem(sys.modules, "cantera", _fake_cantera())
    return get_property_provider(request.param)


def test_gas_constant_from_library(adapter) -> None:
    assert adapter.R == pytest.approx(8.314462618 / 28.97e-3, rel=1e-12)


def test_re_referenced(adapter) -> None:
    assert adapter.h(298.15) == pytest.approx(0.0, abs=1e-6)
    assert adapter.s(298.15, P_REF) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("T", [300.0, 900.0, 1500.0])
def test_matches_underlying_data(adapter, T: float) -> None:
    assert adapter.h(T) == pytest.approx(_VC.h(T), rel=1e-12, abs=1e-6)
    assert adapter.cp(T) == pytest.approx(_VC.cp(T), rel=1e-12)
    assert adapter.s(T, 10 * P_REF) == pytest.approx(_VC.s(T, 10 * P_REF), rel=1e-4, abs=0.1)


@pytest.mark.parametrize("T", [300.0, 900.0, 1500.0])
def test_inverse_roundtrip(adapter, T: float) -> None:
    assert abs(adapter.T_from_h(adapter.h(T)) - T) < 1e-8
    P = 14 * P_REF
    assert abs(adapter.T_from_s_P(adapter.s(T, P), P) - T) < 1e-8


def test_range_enforced(adapter) -> None:
    with pytest.raises(ValueError):
        adapter.h(10.0)
