"""Component tests (REQ-F01, REQ-F02, REQ-T02), parametrized over providers."""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from brayton_cycle.components import Combustor, CombustorMode, Compressor, HeatRejection, Turbine
from brayton_cycle.core import PropertyProvider
from brayton_cycle.core.constants import P_REF
from brayton_cycle.core.exceptions import (
    BraytonError,
    CombustorTemperatureError,
    CycleClosureError,
    FuelAirRatioError,
    InputValidationError,
    InvalidEfficiencyError,
    InvalidPressureLossError,
    InvalidPressureRatioError,
    MassConservationError,
)
from brayton_cycle.properties import ConstantCpProvider, VariableCpProvider

ROOT = Path(__file__).resolve().parents[1]
REF = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))["cases"]
LHV = 43.0e6
T1, P1, RP = 288.15, P_REF, 14.0


@pytest.fixture(params=["constant-cp", "variable-cp"])
def gas(request: pytest.FixtureRequest) -> PropertyProvider:
    return ConstantCpProvider() if request.param == "constant-cp" else VariableCpProvider()


def _comb(gas: PropertyProvider, **kw: object) -> Combustor:
    base: dict[str, object] = dict(eta_comb=0.99, dp_comb=0.03, lhv=LHV)
    base.update(kw)
    mode = CombustorMode.TARGET_T3 if "T3" in base else CombustorMode.FUEL_AIR_RATIO
    return Combustor(gas, mode, **base)  # type: ignore[arg-type]


def _st2(gas: PropertyProvider, eta_c: float = 0.86):
    return Compressor(gas, RP, eta_c).process(gas.state(T1, P1, "1"))


# ---------------------------------------------------------------- Second Law
@pytest.mark.parametrize("eta", [0.6, 0.86, 0.99])
def test_compressor_sgen_positive(gas: PropertyProvider, eta: float) -> None:
    r = _st2(gas, eta)
    assert r.s_gen > 0.0
    assert r.energy_residual == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("eta", [0.6, 0.89, 0.99])
def test_turbine_sgen_positive(gas: PropertyProvider, eta: float) -> None:
    r = Turbine(gas, P1, eta).process(gas.state(1500.0, 13.58 * P1, "3"))
    assert r.s_gen > 0.0 and r.work > 0.0
    assert r.energy_residual == pytest.approx(0.0, abs=1e-6)


def test_combustor_and_rejection_sgen_positive(gas: PropertyProvider) -> None:
    r2 = _st2(gas)
    r3 = _comb(gas, T3=1500.0).process(r2.outlet)
    r4 = Turbine(gas, P1, 0.89).process(r3.outlet)
    r1 = HeatRejection(gas, T1, P1).process(r4.outlet)
    assert r3.s_gen > 0.0 and r1.s_gen > 0.0
    for r in (r3, r1):
        assert r.energy_residual == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("machine", ["compressor", "turbine"])
def test_isentropic_when_eta_one(gas: PropertyProvider, machine: str) -> None:
    if machine == "compressor":
        r = Compressor(gas, RP, 1.0).process(gas.state(T1, P1, "1"))
    else:
        r = Turbine(gas, P1, 1.0).process(gas.state(1500.0, RP * P1, "3"))
    assert r.s_gen == pytest.approx(0.0, abs=1e-8)
    assert r.isentropic_outlet is not None
    assert r.outlet.T == pytest.approx(r.isentropic_outlet.T, abs=1e-8)


# --------------------------------------------------- isentropic reproduction
def test_eta_one_reproduces_closed_form_cold_air() -> None:
    gas = ConstantCpProvider()
    k = 1.4
    r2 = Compressor(gas, 10.0, 1.0).process(gas.state(300.0, P1, "1"))
    r4 = Turbine(gas, P1, 1.0).process(gas.state(1400.0, 10 * P1, "3"))
    assert r2.outlet.T == pytest.approx(300.0 * 10 ** ((k - 1) / k), rel=1e-12)
    assert r4.outlet.T == pytest.approx(1400.0 / 10 ** ((k - 1) / k), rel=1e-12)


def test_eta_one_reproduces_variable_cp_isentrope() -> None:
    gas = VariableCpProvider()
    r2 = Compressor(gas, RP, 1.0).process(gas.state(T1, P1, "1"))
    assert gas.s(r2.outlet.T, RP * P1) == pytest.approx(gas.s(T1, P1), abs=1e-9)


# ---------------------------------------------- reference cases (non-circular)
@pytest.mark.parametrize("case", ["A_ideal_cold_air", "B_irreversible_variable_cp"])
def test_component_chain_matches_reference(case: str) -> None:
    c = REF[case]
    i, e = c["inputs"], c["expected"]
    gas: PropertyProvider = (ConstantCpProvider(i["cp"], i["k"]) if case.startswith("A")
                             else VariableCpProvider())
    lhv, m = i.get("lhv", LHV), i.get("mdot", 1.0)
    r2 = Compressor(gas, i["rp"], i["eta_c"], m).process(gas.state(i["T1"], i["P1"], "1"))
    r3 = Combustor(gas, "target_T3", T3=i["T3"], eta_comb=i["eta_comb"],
                   dp_comb=i["dp_comb"], lhv=lhv, mass_flow=m).process(r2.outlet)
    r4 = Turbine(gas, i["P1"], i["eta_t"], m).process(r3.outlet)
    r1 = HeatRejection(gas, i["T1"], i["P1"], m).process(r4.outlet, mass_flow_in=r4.mass_flow)
    assert Compressor.compressor_work(r2) == pytest.approx(e["w_c"], rel=1e-8)
    assert r4.work == pytest.approx(e["w_t"], rel=1e-8)
    assert r3.heat == pytest.approx(e["q_in"], rel=1e-8)
    assert -r1.heat == pytest.approx(e["q_out"], rel=1e-8)
    for r, key in [(r2, "compressor"), (r3, "combustor"), (r4, "turbine"), (r1, "heat_rejection")]:
        assert r.s_gen == pytest.approx(e["s_gen"][key], abs=1e-6)
    if case.startswith("B"):
        assert r3.fuel_air_ratio == pytest.approx(e["fuel_air_ratio"], rel=1e-8)
        assert Compressor.compressor_power(r2) == pytest.approx(m * e["w_c"], rel=1e-8)
        assert r3.heat_rate == pytest.approx(m * e["q_in"], rel=1e-8)


# ----------------------------------------------------------------- combustor
def test_combustor_mode_roundtrip(gas: PropertyProvider) -> None:
    st2 = _st2(gas).outlet
    ra = _comb(gas, T3=1500.0).process(st2)
    assert ra.fuel_air_ratio is not None
    rb = _comb(gas, fuel_air_ratio=ra.fuel_air_ratio).process(st2)
    assert rb.outlet.T == pytest.approx(1500.0, abs=1e-8)
    assert rb.outlet.P == ra.outlet.P and rb.s_gen == pytest.approx(ra.s_gen, abs=1e-8)


def test_combustor_energy_balance(gas: PropertyProvider) -> None:
    r = _comb(gas, fuel_air_ratio=0.02).process(_st2(gas).outlet)
    assert r.heat == pytest.approx(0.99 * 0.02 * LHV, rel=1e-12)


@pytest.mark.parametrize("dp", [0.0, 0.03, 0.10])
def test_pressure_loss_formula(gas: PropertyProvider, dp: float) -> None:
    st2 = _st2(gas).outlet
    r = _comb(gas, T3=1500.0, dp_comb=dp).process(st2)
    assert r.outlet.P == pytest.approx(st2.P * (1.0 - dp), rel=1e-15)


def test_combustor_explicit_T_source_increases_sgen(gas: PropertyProvider) -> None:
    st2 = _st2(gas).outlet
    base = _comb(gas, T3=1500.0).process(st2).s_gen
    hot = _comb(gas, T3=1500.0, T_source=2200.0).process(st2).s_gen
    assert hot > base > 0.0


def test_fuel_flow(gas: PropertyProvider) -> None:
    c = _comb(gas, fuel_air_ratio=0.02, mass_flow=25.0)
    assert c.fuel_flow(c.process(_st2(gas).outlet)) == pytest.approx(0.5)


# ------------------------------------------------------------ heat rejection
def test_heat_rejection_closes_cycle(gas: PropertyProvider) -> None:
    st4 = gas.state(850.0, P1, "4")
    r = HeatRejection(gas, T1, P1, 25.0).process(st4, mass_flow_in=25.0)
    assert (r.outlet.T, r.outlet.P, r.outlet.label) == (T1, P1, "1")
    assert -r.heat == pytest.approx(st4.h - gas.h(T1), rel=1e-12)


def test_heat_rejection_mass_conservation(gas: PropertyProvider) -> None:
    with pytest.raises(MassConservationError):
        HeatRejection(gas, T1, P1, 25.0).process(gas.state(850.0, P1), mass_flow_in=25.6)


@pytest.mark.parametrize(("T4", "P4"), [(850.0, 1.2 * P_REF), (280.0, P_REF)])
def test_heat_rejection_closure_errors(gas: PropertyProvider, T4: float, P4: float) -> None:
    with pytest.raises(CycleClosureError):
        HeatRejection(gas, T1, P1).process(gas.state(T4, P4))


# ------------------------------------------------------------ invalid inputs
@pytest.mark.parametrize(
    ("factory", "exc"),
    [
        (lambda g: Compressor(g, 14.0, 0.0), InvalidEfficiencyError),
        (lambda g: Compressor(g, 14.0, 1.01), InvalidEfficiencyError),
        (lambda g: Compressor(g, 14.0, math.nan), InvalidEfficiencyError),
        (lambda g: Compressor(g, 1.0, 0.86), InvalidPressureRatioError),
        (lambda g: Compressor(g, 0.5, 0.86), InvalidPressureRatioError),
        (lambda g: Compressor(g, 14.0, 0.86, mass_flow=-1.0), InputValidationError),
        (lambda g: Turbine(g, P1, -0.1), InvalidEfficiencyError),
        (lambda g: Turbine(g, 0.0, 0.9), InvalidPressureRatioError),
        (lambda g: _comb(g, T3=1500.0, dp_comb=1.0), InvalidPressureLossError),
        (lambda g: _comb(g, T3=1500.0, dp_comb=-0.01), InvalidPressureLossError),
        (lambda g: _comb(g, T3=1500.0, eta_comb=1.2), InvalidEfficiencyError),
        (lambda g: _comb(g, T3=1500.0, lhv=0.0), InputValidationError),
        (lambda g: _comb(g, fuel_air_ratio=0.0), FuelAirRatioError),
        (lambda g: _comb(g, fuel_air_ratio=0.2), FuelAirRatioError),
        (lambda g: Combustor(g, "target_T3", eta_comb=0.99, dp_comb=0.03, lhv=LHV),
         InputValidationError),
        (lambda g: Combustor(g, "target_T3", T3=1500.0, fuel_air_ratio=0.02,
                             eta_comb=0.99, dp_comb=0.03, lhv=LHV), InputValidationError),
        (lambda g: Combustor(g, "plasma", T3=1500.0, eta_comb=0.99, dp_comb=0.03, lhv=LHV),
         InputValidationError),
        (lambda g: HeatRejection(g, T1, P1, T_sink=300.0), InputValidationError),
    ],
)
def test_invalid_constructor_inputs(gas: PropertyProvider, factory, exc) -> None:
    with pytest.raises(exc):
        factory(gas)


def test_target_T3_not_above_T2(gas: PropertyProvider) -> None:
    st2 = _st2(gas).outlet
    with pytest.raises(CombustorTemperatureError):
        _comb(gas, T3=st2.T - 1.0).process(st2)


def test_target_T3_needs_too_much_fuel(gas: PropertyProvider) -> None:
    st2 = _st2(gas).outlet
    with pytest.raises(FuelAirRatioError):
        _comb(gas, T3=1700.0, lhv=10.0e6).process(st2)


def test_turbine_needs_expansion(gas: PropertyProvider) -> None:
    with pytest.raises(InvalidPressureRatioError):
        Turbine(gas, 2 * P1, 0.9).process(gas.state(1500.0, P1))


def test_T_source_below_T3_rejected(gas: PropertyProvider) -> None:
    with pytest.raises(InputValidationError):
        _comb(gas, T3=1500.0, T_source=1400.0).process(_st2(gas).outlet)


def test_all_errors_share_base_class() -> None:
    for exc in (InvalidEfficiencyError, FuelAirRatioError, MassConservationError,
                CycleClosureError, CombustorTemperatureError):
        assert issubclass(exc, BraytonError)


# ------------------------------------------------------------ design rules
COMP_DIR = ROOT / "brayton_cycle" / "components"


def test_components_do_not_import_concrete_backends() -> None:
    for f in COMP_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("brayton_cycle.properties"), f.name


def _code_lines(src: str) -> int:
    """Lines of code excluding docstrings, comments and blank lines."""
    tree = ast.parse(src)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                doc_lines.update(range(first.lineno, first.end_lineno + 1))
    return sum(1 for i, line in enumerate(src.splitlines(), 1)
               if i not in doc_lines and line.strip() and not line.strip().startswith("#"))


def test_component_files_are_small() -> None:
    """Spec: each component file under ~120 lines; measured on code (docs are free)."""
    for f in COMP_DIR.glob("*.py"):
        assert _code_lines(f.read_text(encoding="utf-8")) <= 100, f.name
