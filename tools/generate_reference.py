#!/usr/bin/env python3
"""Generate ``validation_reference_data.json`` independently of the solver.

Independence rules (so validation is NOT circular):
  * standard library only (math, json) - no numpy/scipy, no ``brayton_cycle`` import;
  * all inputs and constants are re-typed here from the primary references,
    so a typo in ``brayton_cycle/core/constants.py`` is caught by the tests
    (tests/test_constants.py cross-checks both against this JSON);
  * closed-form hand-calculation formulas; the only iteration is a plain
    bisection used to invert the published Table A-2c polynomial.

Usage:  python tools/generate_reference.py [output_path]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Inputs re-typed from references (see docs/references.md)
# --------------------------------------------------------------------------
R_U = 8.314462618        # J/(mol K)            [8]
M_AIR = 28.97e-3         # kg/mol               [1] Table A-1
R_AIR = 287.0            # J/(kg K)             [1] Table A-1
CP_300 = 1005.0          # J/(kg K)             [1] Table A-2a
K_300 = 1.4              # -                    [1] Table A-2a
# Table A-2c air: cp_bar = a + bT + cT^2 + dT^3, kJ/(kmol K) == J/(mol K), T in K
A, B, C, D = 28.11, 0.1967e-2, 0.4802e-5, -1.966e-9   # [1] Table A-2c (as published)
T_REF = 298.15           # K                    [1] Ch. 15 reference state
P_REF = 101325.0         # Pa                   [1] Ch. 15; 1 atm (definitional, FLAG)


# --------------------------------------------------------------------------
# Hand-calc property models
# --------------------------------------------------------------------------
def bisect(fun, lo: float, hi: float, tol: float = 1e-12, maxit: int = 200) -> float:
    """Plain bisection root finder (independent of scipy)."""
    flo = fun(lo)
    if flo * fun(hi) > 0.0:
        raise ValueError("root not bracketed")
    for _ in range(maxit):
        mid = 0.5 * (lo + hi)
        fm = fun(mid)
        if fm == 0.0 or (hi - lo) < tol:
            return mid
        if flo * fm < 0.0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


class ConstCp:
    """Cold-air standard: constant cp, R = cp (1 - 1/k) for self-consistency."""

    def __init__(self, cp: float, k: float) -> None:
        self.cp, self.k = cp, k
        self.R = cp * (1.0 - 1.0 / k)

    def h(self, T: float) -> float:
        return self.cp * (T - T_REF)

    def s0(self, T: float) -> float:
        return self.cp * math.log(T / T_REF)

    def T_from_h(self, h: float) -> float:
        return T_REF + h / self.cp

    def T_from_s0(self, s0: float) -> float:
        return T_REF * math.exp(s0 / self.cp)


class PolyCp:
    """Variable cp from Cengel Table A-2c, integrated analytically."""

    R = R_AIR

    def cp(self, T: float) -> float:
        return (A + B * T + C * T**2 + D * T**3) / M_AIR

    def h(self, T: float) -> float:
        Tr = T_REF
        hb = (A * (T - Tr) + B / 2 * (T**2 - Tr**2) + C / 3 * (T**3 - Tr**3)
              + D / 4 * (T**4 - Tr**4))
        return hb / M_AIR

    def s0(self, T: float) -> float:
        Tr = T_REF
        sb = (A * math.log(T / Tr) + B * (T - Tr) + C / 2 * (T**2 - Tr**2)
              + D / 3 * (T**3 - Tr**3))
        return sb / M_AIR

    def T_from_h(self, h: float) -> float:
        return bisect(lambda T: self.h(T) - h, 100.0, 3000.0)

    def T_from_s0(self, s0: float) -> float:
        return bisect(lambda T: self.s0(T) - s0, 100.0, 3000.0)


def solve_cycle(gas, T1, P1, rp, T3, eta_c, eta_t, eta_comb, dp_comb, lhv=None, mdot=None):
    """Hand-calc of the 4-station air-standard cycle; returns a result dict."""
    s = lambda T, P: gas.s0(T) - gas.R * math.log(P / P_REF)  # noqa: E731
    P2 = rp * P1
    P3 = P2 * (1.0 - dp_comb)
    P4 = P1
    h1 = gas.h(T1)
    # compressor
    T2s = gas.T_from_s0(gas.s0(T1) + gas.R * math.log(P2 / P1))
    h2s = gas.h(T2s)
    w_c = (h2s - h1) / eta_c
    h2 = h1 + w_c
    T2 = gas.T_from_h(h2)
    # combustor (target-T3 mode)
    h3 = gas.h(T3)
    q_in = h3 - h2
    f = q_in / (eta_comb * lhv) if lhv else None
    # turbine
    T4s = gas.T_from_s0(gas.s0(T3) - gas.R * math.log(P3 / P4))
    h4s = gas.h(T4s)
    w_t = eta_t * (h3 - h4s)
    h4 = h3 - w_t
    T4 = gas.T_from_h(h4)
    q_out = h4 - h1
    w_net = w_t - w_c
    s1, s2, s3, s4 = s(T1, P1), s(T2, P2), s(T3, P3), s(T4, P4)
    sgen = {
        "compressor": s2 - s1,
        "combustor": (s3 - s2) - q_in / T3,       # T_source = T3 assumption
        "turbine": s4 - s3,
        "heat_rejection": (s1 - s4) + q_out / T1,  # T_sink = T1 assumption
    }
    sgen["total"] = sum(sgen.values())
    st = lambda lab, T, P, h, ss: {"label": lab, "T": T, "P": P, "h": h, "s": ss}  # noqa: E731
    out = {
        "states": [
            st("1", T1, P1, h1, s1),
            st("2s", T2s, P2, h2s, s(T2s, P2)),
            st("2", T2, P2, h2, s2),
            st("3", T3, P3, h3, s3),
            st("4s", T4s, P4, h4s, s(T4s, P4)),
            st("4", T4, P4, h4, s4),
        ],
        "w_c": w_c, "w_t": w_t, "w_net": w_net, "q_in": q_in, "q_out": q_out,
        "bwr": w_c / w_t, "eta_th": w_net / q_in,
        "first_law_residual": abs((q_in - q_out) - w_net) / q_in,
        "s_gen": sgen,
        "fuel_air_ratio": f,
        "sfc_kg_per_kWh": 3.6e6 * f / w_net if f else None,
    }
    if mdot is not None:
        out["net_power_W"] = mdot * w_net
        out["fuel_flow_kg_per_s"] = mdot * f if f else None
    return out


def build() -> dict:
    # ---------------- Case A: ideal cold-air ----------------
    gA = ConstCp(CP_300, K_300)
    inA = dict(T1=300.0, P1=101325.0, rp=10.0, T3=1400.0,
               eta_c=1.0, eta_t=1.0, eta_comb=1.0, dp_comb=0.0)
    resA = solve_cycle(gA, **inA)
    k = K_300
    resA["analytical"] = {
        "eta_th_cold_air": 1.0 - inA["rp"] ** ((1.0 - k) / k),
        "T2_closed_form": inA["T1"] * inA["rp"] ** ((k - 1.0) / k),
        "T4_closed_form": inA["T3"] / inA["rp"] ** ((k - 1.0) / k),
        "rp_opt_w_net": (inA["T3"] / inA["T1"]) ** (k / (2.0 * (k - 1.0))),
        "w_net_max": CP_300 * (math.sqrt(inA["T3"]) - math.sqrt(inA["T1"])) ** 2,
    }
    # ---------------- Case B: irreversible variable-cp ----------------
    gB = PolyCp()
    inB = dict(T1=288.15, P1=101325.0, rp=14.0, T3=1500.0, eta_c=0.86, eta_t=0.89,
               eta_comb=0.99, dp_comb=0.03, lhv=43.0e6, mdot=25.0)
    resB = solve_cycle(gB, **inB)

    return {
        "schema_version": "1.0",
        "generator": "tools/generate_reference.py (stdlib-only, independent of brayton_cycle)",
        "units": {"T": "K", "P": "Pa", "h": "J/kg", "s": "J/(kg*K)", "w,q": "J/kg",
                  "sfc": "kg/kWh", "power": "W", "mass_flow": "kg/s"},
        "reference_state": {"T_ref": T_REF, "P_ref": P_REF,
                            "citation": "[1] Ch. 15; P_ref 1 atm definitional [FLAG]"},
        "assumptions": [
            "Air-standard: working fluid is air at all stations; fuel mass addition "
            "is neglected in the turbine mass flow (f only used for SFC / fuel flow).",
            "Steady flow, adiabatic compressor and turbine, KE and PE neglected.",
            "Combustor heat supplied from a source at T_source = T3 (max cycle temperature).",
            "Heat rejected to a sink at T_sink = T1 (ambient).",
            "P4 = P1 (no exhaust pressure loss); combustor loss P3 = P2 (1 - dP_comb).",
            "Combustor solved in target-T3 mode; the reported f is the input for the "
            "fuel-air-ratio-mode test, which must reproduce T3.",
        ],
        "cases": {
            "A_ideal_cold_air": {
                "description": "Ideal cold-air-standard Brayton cycle (constant cp, k).",
                "property_model": "constant-cp, cp = 1005 J/(kg K), k = 1.4, "
                                  "R = cp(1 - 1/k) = 287.142857 J/(kg K) for exact "
                                  "isentropic consistency (Table A-1 R = 287.0 differs by 0.05 %).",
                "inputs": {**inA, "cp": CP_300, "k": K_300},
                "input_citations": {
                    "T1, P1, rp, T3": "assignment specification (textbook-style example values)",
                    "eta = 1, dP = 0": "ideal-cycle definition, [1] Ch. 9",
                    "cp, k": "[1] Table A-2a (300 K)",
                },
                "expected": resA,
                "tolerances": {
                    "rel_tol_states_and_energies": 1e-9,
                    "abs_tol_s_gen": 1e-9,
                    "rel_tol_vs_analytical_eta": 1e-12,
                    "note": "Closed-form model: solver must match to round-off (REQ-N02).",
                },
            },
            "B_irreversible_variable_cp": {
                "description": "Irreversible cycle, variable cp from Table A-2c polynomial.",
                "property_model": "variable-cp, [1] Table A-2c air polynomial, T in K, "
                                  "coefficients exactly as published; R = 287.0 J/(kg K) [1] Table A-1.",
                "inputs": inB,
                "input_citations": {
                    "T1 = 288.15 K, P1 = 101325 Pa": "sea-level standard atmosphere "
                        "[FLAG: ISO 2533 not in reference list]",
                    "rp, T3, mdot": "assignment specification",
                    "eta_c, eta_t, eta_comb, dP_comb": "assignment specification; typical "
                        "ranges per [7] [FLAG: page to record]",
                    "LHV": "[7] kerosene ~43 MJ/kg",
                    "cp polynomial": "[1] Table A-2c",
                },
                "expected": resB,
                "tolerances": {
                    "rel_tol_temperatures": 1e-6,
                    "rel_tol_energies": 1e-6,
                    "abs_tol_entropy": 1e-4,
                    "first_law_residual_max": 1e-6,
                    "rel_tol_vs_coolprop_cantera": 1.5e-2,
                    "note": "Same polynomial -> only root-finder tolerance differs. "
                            "Cross-backend tolerance reflects the 0.72 % polynomial error "
                            "plus real-gas/composition differences [2][3][4].",
                },
            },
        },
        "table_A17_spot_checks": {
            "purpose": "Day-5 validation of the variable-cp backend against tabulated air "
                       "properties. Compare DIFFERENCES only (A-17 datum differs from T_ref).",
            "citation": "[1] Table A-17",
            "status": "FLAG: transcribed without the printed table at hand - verify "
                      "against your edition before relying on them.",
            "points_kJ_per_kg": [
                {"T": 300.0, "h": 300.19, "s0": 1.70203},
                {"T": 1000.0, "h": 1046.04, "s0": 2.96770},
                {"T": 1500.0, "h": 1635.97, "s0": 3.44516},
            ],
            "tolerance_rel_on_differences": 1.0e-2,
        },
    }


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "validation_reference_data.json"
    data = build()
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for name, case in data["cases"].items():
        e = case["expected"]
        print(f"{name}: w_net={e['w_net']/1e3:.3f} kJ/kg  eta_th={e['eta_th']:.5f}  "
              f"residual={e['first_law_residual']:.2e}  s_gen_total={e['s_gen']['total']:.4f}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
