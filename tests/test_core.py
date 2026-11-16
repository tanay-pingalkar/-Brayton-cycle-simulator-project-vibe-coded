"""Day-1 tests for the core data model (REQ-F01, REQ-T02 enforcement)."""

from __future__ import annotations

import dataclasses
import math

import pytest

from brayton_cycle.core import ComponentResult, PropertyProvider, SecondLawViolation, State


class _ToyProvider(PropertyProvider):
    """Minimal constant-cp provider used only to exercise the ABC helpers."""

    name = "toy"
    _cp = 1005.0

    @property
    def R(self) -> float:
        return 287.0

    def cp(self, T: float) -> float:
        return self._cp

    def h(self, T: float) -> float:
        return self._cp * (T - 298.15)

    def s(self, T: float, P: float) -> float:
        return self._cp * math.log(T / 298.15) - self.R * math.log(P / 101325.0)

    def T_from_h(self, h: float) -> float:
        return 298.15 + h / self._cp

    def T_from_s_P(self, s: float, P: float) -> float:
        return 298.15 * math.exp((s + self.R * math.log(P / 101325.0)) / self._cp)


def test_state_is_frozen() -> None:
    st = State(T=300.0, P=101325.0, h=0.0, s=0.0, label="1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        st.T = 400.0  # type: ignore[misc]


@pytest.mark.parametrize("kwargs", [dict(T=-1.0), dict(P=0.0), dict(h=math.nan)])
def test_state_rejects_invalid(kwargs: dict[str, float]) -> None:
    base = dict(T=300.0, P=101325.0, h=0.0, s=0.0)
    base.update(kwargs)
    with pytest.raises(ValueError):
        State(**base)


def test_provider_helpers_roundtrip() -> None:
    p = _ToyProvider()
    st = p.state(600.0, 1.0e6, "2")
    assert p.state_from_h_P(st.h, st.P).T == pytest.approx(600.0, rel=1e-12)
    assert p.state_from_s_P(st.s, st.P).T == pytest.approx(600.0, rel=1e-12)
    assert p.gamma(600.0) == pytest.approx(1005.0 / 718.0)
    assert p.v(300.0, 101325.0) == pytest.approx(287.0 * 300.0 / 101325.0)


def test_cannot_instantiate_abstract() -> None:
    with pytest.raises(TypeError):
        PropertyProvider()  # type: ignore[abstract]


def test_negative_sgen_raises() -> None:
    a = State(300.0, 1e5, 0.0, 0.0, "1")
    b = State(310.0, 1e5, 1e4, 1.0, "2")
    with pytest.raises(SecondLawViolation):
        ComponentResult("bad", a, b, work=-1e4, heat=0.0, s_gen=-1e-3)


def test_component_result_energy_residual() -> None:
    a = State(300.0, 1e5, 0.0, 0.0, "1")
    b = State(580.0, 1e6, 2.8e5, 0.0, "2")
    r = ComponentResult("compressor", a, b, work=-2.8e5, heat=0.0, s_gen=0.0)
    assert r.energy_residual == pytest.approx(0.0, abs=1e-9)
