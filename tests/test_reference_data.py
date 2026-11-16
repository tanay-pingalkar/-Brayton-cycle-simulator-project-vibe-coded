"""Sanity of the independent reference data (REQ-N01, REQ-N02, REQ-T02)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))
CASES = DATA["cases"]


@pytest.mark.parametrize("name", list(CASES))
def test_reference_first_law(name: str) -> None:
    assert CASES[name]["expected"]["first_law_residual"] < 1e-6


@pytest.mark.parametrize("name", list(CASES))
def test_reference_second_law(name: str) -> None:
    for cv, sg in CASES[name]["expected"]["s_gen"].items():
        assert sg >= -1e-9, cv


def test_case_A_matches_closed_form() -> None:
    e = CASES["A_ideal_cold_air"]["expected"]
    an = e["analytical"]
    states = {s["label"]: s for s in e["states"]}
    assert e["eta_th"] == pytest.approx(an["eta_th_cold_air"], rel=1e-12)
    assert states["2"]["T"] == pytest.approx(an["T2_closed_form"], rel=1e-12)
    assert states["4"]["T"] == pytest.approx(an["T4_closed_form"], rel=1e-12)
    assert an["rp_opt_w_net"] == pytest.approx(14.817, rel=1e-4)


def test_case_B_physically_plausible() -> None:
    e = CASES["B_irreversible_variable_cp"]["expected"]
    assert 0.30 < e["eta_th"] < 0.45
    assert 0.015 < e["fuel_air_ratio"] < 0.03
    assert e["s_gen"]["compressor"] > 0 and e["s_gen"]["turbine"] > 0


def test_generator_is_reproducible(tmp_path: Path) -> None:
    out = tmp_path / "ref.json"
    subprocess.run([sys.executable, str(ROOT / "tools" / "generate_reference.py"), str(out)],
                   check=True, capture_output=True)
    assert json.loads(out.read_text(encoding="utf-8")) == DATA


def test_generator_does_not_import_package() -> None:
    import ast

    tree = ast.parse((ROOT / "tools" / "generate_reference.py").read_text(encoding="utf-8"))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"__future__", "json", "math", "sys", "pathlib"}, mods
