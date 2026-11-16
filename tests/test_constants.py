"""Constants: citation discipline and cross-check vs. independent reference (REQ-D01)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from brayton_cycle.core import constants as k

ROOT = Path(__file__).resolve().parents[1]
CONST_SRC = ROOT / "brayton_cycle" / "core" / "constants.py"
TAG = re.compile(r"\[(\d+)\]|\[FLAG:|REQ-[A-Z]\d{2}|Definitional", re.IGNORECASE)


def test_every_constant_cited() -> None:
    """Each module-level constant must be followed by a docstring with a tag."""
    body = ast.parse(CONST_SRC.read_text(encoding="utf-8")).body
    missing = []
    for i, node in enumerate(body):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            nxt = body[i + 1] if i + 1 < len(body) else None
            doc = (nxt.value.value if isinstance(nxt, ast.Expr)
                   and isinstance(nxt.value, ast.Constant) else "")
            if not TAG.search(str(doc)):
                missing.append(node.target.id)
    assert not missing, f"uncited constants: {missing}"


def test_cited_tags_exist_in_references() -> None:
    refs = (ROOT / "docs" / "references.md").read_text(encoding="utf-8")
    tags = set(re.findall(r"\[(\d+)\]", CONST_SRC.read_text(encoding="utf-8")))
    for t in tags:
        assert f"[{t}]" in refs


def test_gas_constant_consistent_with_codata() -> None:
    assert k.R_UNIVERSAL / k.M_AIR == pytest.approx(k.R_AIR, rel=5e-5)


def test_cp_polynomial_not_scaled() -> None:
    """Guard against the T/1000 bug: cp(300 K) must be ~1.004 kJ/(kg K)."""
    T = 300.0
    cp = (k.CP_POLY_AIR_A + k.CP_POLY_AIR_B * T + k.CP_POLY_AIR_C * T**2
          + k.CP_POLY_AIR_D * T**3) / k.M_AIR
    assert cp == pytest.approx(k.CP_AIR_300K, rel=5e-3)


def test_constants_match_reference_inputs() -> None:
    data = json.loads((ROOT / "validation_reference_data.json").read_text(encoding="utf-8"))
    a = data["cases"]["A_ideal_cold_air"]["inputs"]
    b = data["cases"]["B_irreversible_variable_cp"]["inputs"]
    assert a["cp"] == k.CP_AIR_300K and a["k"] == k.GAMMA_AIR_300K
    assert b["lhv"] == k.LHV_KEROSENE and b["T1"] == k.T_AMBIENT_ISA
    assert (b["eta_c"], b["eta_t"], b["eta_comb"], b["dp_comb"]) == (
        k.ETA_C_DEFAULT, k.ETA_T_DEFAULT, k.ETA_COMB_DEFAULT, k.DP_COMB_DEFAULT)
    assert data["reference_state"]["T_ref"] == k.T_REF
    assert data["reference_state"]["P_ref"] == k.P_REF
