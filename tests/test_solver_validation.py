"""End-to-end solver validation (REQ-F01, REQ-N01, REQ-N02).

Reference values come from tools/generate_reference.py (stdlib-only, no
brayton_cycle import), so these comparisons are not circular. Tolerances are
read from the JSON file itself.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from brayton_cycle.core.exceptions import ConservationError, InputValidationError
from brayton_cycle.properties import ConstantCpProvider
from brayton_cycle.solver import STATION_ORDER, BraytonConfig, BraytonResult, BraytonSolver

ROOT = Path(__file__).resolve().parents[1]
REF = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))["cases"]
ENERGIES = ("w_c", "w_t", "w_net", "q_in", "q_out")


def _solve(case: str) -> BraytonResult:
    return BraytonSolver().solve(BraytonConfig.from_reference_case(case))


# --------------------------------------------------------- reference cases
def test_case_A_ideal_cold_air() -> None:
    ref, tol = REF["A_ideal_cold_air"]["expected"], REF["A_ideal_cold_air"]["tolerances"]
    rel, abs_s = tol["rel_tol_states_and_energies"], tol["abs_tol_s_gen"]
    r = _solve("A")
    for st in ref["states"]:
        got = r.states[st["label"]]
        for q in ("T", "P", "h"):
            assert getattr(got, q) == pytest.approx(st[q], rel=rel, abs=1e-6), (st["label"], q)
        assert got.s == pytest.approx(st["s"], rel=rel, abs=abs_s)
    for q in (*ENERGIES, "bwr", "eta_th"):
        assert getattr(r, q) == pytest.approx(ref[q], rel=rel), q
    assert r.eta_th == pytest.approx(ref["analytical"]["eta_th_cold_air"],
                                     rel=tol["rel_tol_vs_analytical_eta"])
    assert r.s_gen["compressor"] == pytest.approx(0.0, abs=abs_s)
    assert r.s_gen["turbine"] == pytest.approx(0.0, abs=abs_s)
    for k, v in ref["s_gen"].items():
        got = r.s_gen_total if k == "total" else r.s_gen[k]
        assert got == pytest.approx(v, rel=rel, abs=abs_s), k


def test_case_B_irreversible_variable_cp() -> None:
    ref = REF["B_irreversible_variable_cp"]["expected"]
    tol = REF["B_irreversible_variable_cp"]["tolerances"]
    r = _solve("B")
    for st in ref["states"]:
        got = r.states[st["label"]]
        assert got.T == pytest.approx(st["T"], rel=tol["rel_tol_temperatures"])
        assert got.P == pytest.approx(st["P"], rel=1e-12)
        assert got.h == pytest.approx(st["h"], rel=tol["rel_tol_energies"], abs=1e-6)
        assert got.s == pytest.approx(st["s"], abs=tol["abs_tol_entropy"])
    for q in (*ENERGIES, "bwr", "eta_th", "fuel_air_ratio"):
        assert getattr(r, q) == pytest.approx(ref[q], rel=tol["rel_tol_energies"]), q
    assert r.sfc == pytest.approx(ref["sfc_kg_per_kWh"], rel=tol["rel_tol_energies"])
    assert r.net_power == pytest.approx(ref["net_power_W"], rel=tol["rel_tol_energies"])
    assert r.fuel_flow == pytest.approx(ref["fuel_flow_kg_per_s"], rel=tol["rel_tol_energies"])
    for k, v in ref["s_gen"].items():
        got = r.s_gen_total if k == "total" else r.s_gen[k]
        assert got == pytest.approx(v, abs=tol["abs_tol_entropy"]), k
    assert r.first_law_residual < tol["first_law_residual_max"]


def test_case_B_fuel_air_ratio_mode_reproduces_T3() -> None:
    """REQ-F02 at system level: feed Case B's f back in mode (b)."""
    ref = REF["B_irreversible_variable_cp"]["expected"]
    cfg = BraytonConfig.from_reference_case("B").replace(
        combustor_mode="fuel_air_ratio", T3=None, fuel_air_ratio=ref["fuel_air_ratio"])
    r = BraytonSolver().solve(cfg)
    assert r.states["3"].T == pytest.approx(1500.0, abs=1e-6)
    assert r.w_net == pytest.approx(ref["w_net"], rel=1e-8)


# ------------------------------------------------------------------ REQ-N02
@pytest.mark.parametrize("rp", [2.0, 5.0, 10.0, 20.0, 40.0, 100.0])
def test_cold_air_limit_efficiency(rp: float) -> None:
    gamma = 1.4
    cfg = BraytonConfig(T1=300.0, P1=101325.0, pressure_ratio=rp, T3=1400.0,
                        provider="constant", provider_options={"gamma": gamma})
    r = BraytonSolver().solve(cfg)
    assert r.eta_th == pytest.approx(1.0 - rp ** ((1.0 - gamma) / gamma), rel=1e-12)


# ------------------------------------------------------------------ REQ-N01
def _random_configs(n: int, seed: int = 20261116) -> list[BraytonConfig]:
    rng = np.random.default_rng(seed)
    cfgs = []
    for i in range(n):
        cfgs.append(BraytonConfig(
            T1=float(rng.uniform(273.0, 310.0)), P1=float(rng.uniform(0.6e5, 1.1e5)),
            pressure_ratio=float(rng.uniform(2.0, 30.0)), T3=float(rng.uniform(1150.0, 1750.0)),
            eta_c=float(rng.uniform(0.75, 1.0)), eta_t=float(rng.uniform(0.75, 1.0)),
            eta_comb=float(rng.uniform(0.9, 1.0)), dp_comb=float(rng.uniform(0.0, 0.08)),
            mass_flow=float(rng.uniform(0.5, 200.0)),
            provider="variable" if i % 2 else "constant",
        ))
    return cfgs


@pytest.mark.parametrize("cfg", _random_configs(30), ids=lambda c: f"rp{c.pressure_ratio:.1f}")
def test_first_law_residual_random(cfg: BraytonConfig) -> None:
    r = BraytonSolver().solve(cfg)
    assert r.first_law_residual < 1e-6
    assert all(s >= -1e-9 for s in r.s_gen.values())
    assert r.s_gen_total == pytest.approx(r.q_out / cfg.T1 - r.q_in / r.states["3"].T,
                                          rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("provider", ["constant", "variable"])
def test_net_power_linear_in_mass_flow(provider: str) -> None:
    base = BraytonConfig.from_reference_case("B").replace(provider=provider, mass_flow=1.0)
    p1 = BraytonSolver().solve(base).net_power
    for m in (0.1, 25.0, 400.0):
        r = BraytonSolver().solve(base.replace(mass_flow=m))
        assert r.net_power == pytest.approx(m * p1, rel=1e-12)
        assert r.w_net == pytest.approx(p1, rel=1e-12)  # specific values unchanged


# ------------------------------------------------------------------ audits
def test_conservation_error_raised_when_tolerance_unmeetable() -> None:
    with pytest.raises(ConservationError):
        BraytonSolver(residual_tol=0.0).solve(BraytonConfig.from_reference_case("B"))


def test_sfc_none_when_no_net_work() -> None:
    cfg = BraytonConfig(T1=300.0, P1=101325.0, pressure_ratio=30.0, T3=1000.0,
                        eta_c=0.75, eta_t=0.75, provider="variable")
    r = BraytonSolver().solve(cfg)
    assert r.w_net < 0.0 and r.sfc is None


# ---------------------------------------------------------- config / result
def test_config_round_trip_and_json(tmp_path: Path) -> None:
    cfg = BraytonConfig.from_reference_case("B")
    assert BraytonConfig.from_dict(cfg.to_dict()) == cfg
    p = tmp_path / "case.json"
    p.write_text(json.dumps(cfg.to_dict()), encoding="utf-8")
    assert BraytonConfig.from_json(p) == cfg


def test_config_aliases() -> None:
    cfg = BraytonConfig.from_dict({"T1": 300, "P1": 1e5, "rp": 8, "T3": 1300, "mdot": 3,
                                   "k": 1.4, "cp": 1005, "provider": "constant"})
    assert (cfg.pressure_ratio, cfg.mass_flow, cfg.provider) == (8.0, 3.0, "constant-cp")
    assert cfg.provider_options == {"gamma": 1.4, "cp": 1005}


@pytest.mark.parametrize("bad", [
    {"T1": 300, "P1": 1e5, "rp": 0.9, "T3": 1300},
    {"T1": 300, "P1": 1e5, "rp": 8, "T3": 1300, "eta_c": 1.5},
    {"T1": 300, "P1": 1e5, "rp": 8},                                       # no T3
    {"T1": 300, "P1": 1e5, "rp": 8, "T3": 1300, "colour": "blue"},          # unknown key
    {"T1": 300, "P1": 1e5, "rp": 8, "mode": "fuel_air_ratio", "f": 0.02, "T3": 1300},
])
def test_config_rejects_invalid(bad: dict) -> None:
    with pytest.raises(InputValidationError):
        BraytonConfig.from_dict(bad)


def test_result_to_dict_is_json_serialisable() -> None:
    d = _solve("B").to_dict()
    text = json.dumps(d, allow_nan=False)
    assert [s["label"] for s in json.loads(text)["states"]] == list(STATION_ORDER)
    assert math.isclose(d["kpis"]["eta_th"], REF["B_irreversible_variable_cp"]["expected"]["eta_th"],
                        rel_tol=1e-8)


def test_explicit_provider_instance_overrides_config() -> None:
    r = BraytonSolver(provider=ConstantCpProvider()).solve(BraytonConfig.from_reference_case("B"))
    assert r.provider_name == "constant-cp"
