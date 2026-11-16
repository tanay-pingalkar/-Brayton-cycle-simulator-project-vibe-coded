"""Property-backend tests (REQ-T01), parametrized over all available providers.

CoolProp and Cantera cases are skipped automatically when the optional
packages are not installed (pytest.importorskip).
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import warnings
from pathlib import Path

import numpy as np
import pytest

from brayton_cycle.core import PropertyProvider
from brayton_cycle.core.constants import CP_AIR_300K, GAMMA_AIR_300K, P_REF, R_AIR
from brayton_cycle.properties import (
    BackendUnavailable,
    ConstantCpProvider,
    PropertyRangeWarning,
    VariableCpProvider,
    available_providers,
    get_property_provider,
    register_provider,
    unregister_provider,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"

# Table A-2c states a max error of 0.72 % [1]. Differences of h and s0 between
# two temperatures can carry at most about that error, so 1 % is a strict but
# fair bound.
A17_REL_TOL = 1.0e-2
CROSS_BACKEND_REL_TOL = 1.0e-2
P_LOW = 1.0e5  # "low pressure" for real-gas cross-checks [Pa]

TEMPS = [300.0, 500.0, 800.0, 1200.0, 1700.0]
PRESSURES = [5.0e4, P_REF, 1.0e6, 4.0e6]


def _make(name: str) -> PropertyProvider:
    if name == "coolprop":
        pytest.importorskip("CoolProp")
    elif name == "cantera":
        pytest.importorskip("cantera")
    return get_property_provider(name)


@pytest.fixture(params=["constant-cp", "variable-cp", "coolprop", "cantera"])
def provider(request: pytest.FixtureRequest) -> PropertyProvider:
    return _make(request.param)


def _load_a17() -> dict[float, tuple[float, float]]:
    with (DATA / "cengel_table_a17.csv").open(encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        return {float(r["T"]): (float(r["h"]) * 1e3, float(r["s0"]) * 1e3) for r in rows}


A17 = _load_a17()
A17_PAIRS = list(itertools.combinations(sorted(A17), 2))


# --------------------------------------------------------------------- generic
@pytest.mark.parametrize("T", TEMPS)
def test_mayer_relation(provider: PropertyProvider, T: float) -> None:
    """cp - cv = R (exact for ideal gases; CoolProp is projected to ideal gas)."""
    assert provider.cp(T) - provider.cv(T) == pytest.approx(provider.R, rel=1e-10)


@pytest.mark.parametrize("T", TEMPS)
def test_cp_is_derivative_of_h(provider: PropertyProvider, T: float) -> None:
    """dh/dT = cp: checks the analytical integral against the cp correlation."""
    dT = 1e-3
    dhdT = (provider.h(T + dT) - provider.h(T - dT)) / (2 * dT)
    assert dhdT == pytest.approx(provider.cp(T), rel=1e-6)


@pytest.mark.parametrize("T", TEMPS)
def test_cp_over_T_is_derivative_of_s(provider: PropertyProvider, T: float) -> None:
    """T (ds/dT)_P = cp: checks the s0 integral."""
    dT = 1e-3
    dsdT = (provider.s(T + dT, P_REF) - provider.s(T - dT, P_REF)) / (2 * dT)
    assert T * dsdT == pytest.approx(provider.cp(T), rel=1e-6)


@pytest.mark.parametrize(("T", "P"), list(itertools.product(TEMPS, PRESSURES)))
def test_isentropic_roundtrip(provider: PropertyProvider, T: float, P: float) -> None:
    """T -> s(T, P) -> T_from_s_P(s, P) within 1e-8 K; same for h."""
    assert abs(provider.T_from_s_P(provider.s(T, P), P) - T) < 1e-8
    assert abs(provider.T_from_h(provider.h(T)) - T) < 1e-8


def test_isentropic_compression_roundtrip(provider: PropertyProvider) -> None:
    """Compress 300 K by r_p = 14, then expand back: must return to 300 K."""
    s1 = provider.s(300.0, P_REF)
    T2s = provider.T_from_s_P(s1, 14 * P_REF)
    T1 = provider.T_from_s_P(provider.s(T2s, 14 * P_REF), P_REF)
    assert abs(T1 - 300.0) < 1e-8


def test_h_monotonic(provider: PropertyProvider) -> None:
    T = np.linspace(280.0, 1790.0, 400)
    h = np.array([provider.h(t) for t in T])
    assert np.all(np.diff(h) > 0.0)


def test_reference_state(provider: PropertyProvider) -> None:
    assert provider.h(298.15) == pytest.approx(0.0, abs=1e-6)
    assert provider.s(298.15, P_REF) == pytest.approx(0.0, abs=1e-9)


def test_entropy_pressure_term(provider: PropertyProvider) -> None:
    assert provider.s(500.0, P_REF) - provider.s(500.0, 10 * P_REF) == pytest.approx(
        provider.R * math.log(10.0), rel=1e-6
    )


# ------------------------------------------------------------- constant-cp
def test_constant_cp_defaults_match_table_a2a() -> None:
    p = ConstantCpProvider()
    g, R = p.gamma(300.0), p.R
    assert p.cp(300.0) == pytest.approx(CP_AIR_300K, rel=1e-12)
    assert g == GAMMA_AIR_300K
    assert p.cp(300.0) == pytest.approx(g * R / (g - 1.0), rel=1e-12)


def test_constant_cp_from_R_gamma() -> None:
    p = ConstantCpProvider.from_R_gamma(R_AIR, 1.4)
    assert p.R == pytest.approx(R_AIR, rel=1e-12)
    assert p.cp(1000.0) == pytest.approx(1.4 * R_AIR / 0.4, rel=1e-12)


def test_constant_cp_reproduces_cold_air_isentrope() -> None:
    """REQ-N02 building block: T2s/T1 = r_p^((k-1)/k) exactly."""
    p = ConstantCpProvider()
    T2s = p.T_from_s_P(p.s(300.0, P_REF), 10 * P_REF)
    assert T2s == pytest.approx(300.0 * 10 ** (0.4 / 1.4), rel=1e-13)


# ------------------------------------------------- variable-cp vs Table A-17
@pytest.mark.parametrize(("Ta", "Tb"), A17_PAIRS)
def test_variable_cp_vs_table_a17(Ta: float, Tb: float) -> None:
    """Delta h and Delta s0 between A-17 rows within 1 % ([1] Table A-2c, 0.72 %)."""
    p = VariableCpProvider()
    dh_tab = A17[Tb][0] - A17[Ta][0]
    ds_tab = A17[Tb][1] - A17[Ta][1]
    assert p.h(Tb) - p.h(Ta) == pytest.approx(dh_tab, rel=A17_REL_TOL)
    assert p.s0(Tb) - p.s0(Ta) == pytest.approx(ds_tab, rel=A17_REL_TOL)


def test_a17_csv_matches_reference_json() -> None:
    ref = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))
    for pt in ref["table_A17_spot_checks"]["points_kJ_per_kg"]:
        h, s0 = A17[pt["T"]]
        assert (h / 1e3, s0 / 1e3) == pytest.approx((pt["h"], pt["s0"]), rel=1e-12)


def test_variable_cp_matches_independent_reference() -> None:
    """Every Case B station from tools/generate_reference.py is reproduced."""
    ref = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))
    p = VariableCpProvider()
    for st in ref["cases"]["B_irreversible_variable_cp"]["expected"]["states"]:
        assert p.h(st["T"]) == pytest.approx(st["h"], rel=1e-9, abs=1e-6)
        assert p.s(st["T"], st["P"]) == pytest.approx(st["s"], abs=1e-6)
        assert p.T_from_h(st["h"]) == pytest.approx(st["T"], rel=1e-9)


# ------------------------------------------------------------ range policy
@pytest.mark.parametrize("T", [200.0, 272.9, 1800.1, 2500.0])
def test_variable_cp_out_of_range_raises(T: float) -> None:
    p = VariableCpProvider()
    with pytest.raises(ValueError, match="validity range"):
        p.cp(T)
    with pytest.raises(ValueError, match="validity range"):
        p.h(T)


def test_variable_cp_inverse_out_of_range_raises() -> None:
    p = VariableCpProvider()
    with pytest.raises(ValueError, match="outside the range"):
        p.T_from_h(p.h(1800.0) + 1.0e4)


def test_variable_cp_extrapolate_warns() -> None:
    p = VariableCpProvider(extrapolate=True)
    with pytest.warns(PropertyRangeWarning):
        h = p.h(2000.0)
    with pytest.warns(PropertyRangeWarning):
        assert p.T_from_h(h) == pytest.approx(2000.0, abs=1e-8)


def test_variable_cp_in_range_is_silent() -> None:
    p = VariableCpProvider(extrapolate=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        p.h(1000.0)


# --------------------------------------------------- optional cross-checks
@pytest.mark.parametrize("backend", ["coolprop", "cantera"])
@pytest.mark.parametrize(("Ta", "Tb"), [(300.0, 1000.0), (300.0, 1500.0), (1000.0, 1500.0)])
def test_cross_backend_delta_h(backend: str, Ta: float, Tb: float) -> None:
    """At low pressure, Delta h matches the Table A-2c backend within 1 %."""
    other = _make(backend)
    ref = VariableCpProvider()
    assert other.h(Tb) - other.h(Ta) == pytest.approx(ref.h(Tb) - ref.h(Ta),
                                                      rel=CROSS_BACKEND_REL_TOL)
    assert other.s(Tb, P_LOW) - other.s(Ta, P_LOW) == pytest.approx(
        ref.s(Tb, P_LOW) - ref.s(Ta, P_LOW), rel=CROSS_BACKEND_REL_TOL)


# ----------------------------------------------------------------- registry
def test_registry_lists_builtins() -> None:
    assert {"constant-cp", "variable-cp", "coolprop", "cantera"} <= set(available_providers())


def test_registry_name_normalisation_and_kwargs() -> None:
    p = get_property_provider("Variable_CP", extrapolate=True)
    assert isinstance(p, VariableCpProvider) and p.extrapolate


def test_registry_unknown_name_lists_options() -> None:
    with pytest.raises(KeyError, match="available: .*constant-cp"):
        get_property_provider("unobtainium")


def test_registry_duplicate_rejected() -> None:
    with pytest.raises(KeyError, match="already registered"):
        register_provider("constant-cp", ConstantCpProvider)


def test_registry_open_closed_extension() -> None:
    """A new backend plugs in without touching any existing module."""

    @register_provider("test-helium")
    class _Helium(ConstantCpProvider):
        name = "test-helium"

        def __init__(self) -> None:
            super().__init__(cp=5193.0, gamma=5.0 / 3.0)

    try:
        p = get_property_provider("test-helium")
        assert p.gamma(300.0) == pytest.approx(5.0 / 3.0)
    finally:
        unregister_provider("test-helium")


@pytest.mark.parametrize(("name", "module"), [("coolprop", "CoolProp"), ("cantera", "cantera")])
def test_missing_optional_backend_message(name: str, module: str,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the package, a helpful BackendUnavailable (an ImportError) is raised."""
    import sys

    monkeypatch.setitem(sys.modules, module, None)  # makes `import module` fail
    if module == "CoolProp":
        monkeypatch.setitem(sys.modules, "CoolProp.CoolProp", None)
    with pytest.raises(BackendUnavailable, match=r"pip install"):
        get_property_provider(name)
