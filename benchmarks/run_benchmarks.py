#!/usr/bin/env python3
"""Verification, validation and runtime benchmarks (REQ-V01).

    python benchmarks/run_benchmarks.py            # everything
    python run_verification_and_benchmarks.py      # same, from the repo root
    python main.py --benchmark                     # same, via the CLI

Steps:
    a) verification: full pytest suite (pass/fail counts) and line coverage
       (pytest-cov if installed, else tools/stdlib_coverage.py);
    b) validation: Case A and Case B vs validation_reference_data.json
       (abs/rel error, stored tolerance, pass/fail), cold-air analytic checks,
       and a variable-cp / CoolProp / Cantera comparison when those are installed;
    c) runtime: timeit medians for one solve per backend, a 30-point 1-D sweep,
       a 12 x 8 2-D sweep and an optimal-r_p search; regression only if a median
       exceeds 10x the stored baseline (benchmarks/baseline.json).

Outputs: benchmarks/results/benchmark_results.{json,md} and docs/validation_report.md.
Exit code 0 if tests pass, all validation rows pass and no regression is found.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import timeit
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brayton_cycle import __version__  # noqa: E402
from brayton_cycle.analysis import ParametricSweepEngine  # noqa: E402
from brayton_cycle.core.exceptions import BackendUnavailable  # noqa: E402
from brayton_cycle.properties import get_property_provider  # noqa: E402
from brayton_cycle.solver import BraytonConfig, BraytonSolver  # noqa: E402

RESULTS_DIR = ROOT / "benchmarks" / "results"
BASELINE_FILE = ROOT / "benchmarks" / "baseline.json"
REFERENCE_FILE = ROOT / "validation_reference_data.json"
VALIDATION_DOC = ROOT / "docs" / "validation_report.md"
REGRESSION_FACTOR = 10.0
ALL_PROVIDERS = ("constant", "variable", "coolprop", "cantera")


# ------------------------------------------------------------------ machine
def machine_info() -> dict[str, Any]:
    """Platform, interpreter and library versions."""
    import matplotlib
    import numpy
    import pandas
    import scipy

    return {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "brayton_cycle": __version__,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "numpy": numpy.__version__, "scipy": scipy.__version__,
        "pandas": pandas.__version__, "matplotlib": matplotlib.__version__,
        "optional_backends": {name: _available(name) for name in ("coolprop", "cantera")},
    }


def _available(provider: str) -> bool:
    try:
        get_property_provider(provider)
        return True
    except BackendUnavailable:
        return False


# ------------------------------------------------------------- verification
def run_verification(coverage: bool = True) -> dict[str, Any]:
    """Run the pytest suite in a subprocess; parse JUnit XML (and coverage) results."""
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        cov_json = Path(tmp) / "coverage.json"
        test_args = ["-q", "-p", "no:cacheprovider", f"--junitxml={junit}", str(ROOT / "tests")]
        tool = None
        if coverage and importlib.util.find_spec("pytest_cov") is not None:
            cmd = [sys.executable, "-m", "pytest", "--cov=brayton_cycle",
                   f"--cov-report=json:{cov_json}", *test_args]
            tool = "pytest-cov"
        elif coverage and sys.version_info >= (3, 12):
            cmd = [sys.executable, str(ROOT / "tools" / "stdlib_coverage.py"),
                   "--json", str(cov_json), *test_args]
            tool = "tools/stdlib_coverage.py (sys.monitoring)"
        else:
            cmd = [sys.executable, "-m", "pytest", *test_args]
        start = timeit.default_timer()
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        duration = timeit.default_timer() - start
        suite = ET.parse(junit).getroot()
        suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
        assert suite is not None
        n = {k: int(suite.get(k, 0)) for k in ("tests", "failures", "errors", "skipped")}
        out: dict[str, Any] = {
            "command": " ".join(Path(c).name if os.sep in c else c for c in cmd[:3]),
            "returncode": proc.returncode, "duration_s": duration, "tests": n["tests"],
            "passed": n["tests"] - n["failures"] - n["errors"] - n["skipped"],
            "failed": n["failures"], "errors": n["errors"], "skipped": n["skipped"],
            "summary_line": next((ln.strip(" =") for ln in reversed(proc.stdout.splitlines())
                                  if " passed" in ln or " failed" in ln or " error" in ln), ""),
        }
        if tool and cov_json.exists():
            out["coverage"] = _coverage_summary(json.loads(cov_json.read_text()), tool)
    return out


def _coverage_summary(data: dict[str, Any], tool: str) -> dict[str, Any]:
    if "packages" in data:  # stdlib tool format
        pk = {k: round(v["percent"], 1) for k, v in data["packages"].items()}
        return {"tool": tool, "total_percent": round(data["total_percent"], 1),
                "non_gui_percent": round(data["non_gui_percent"], 1), "packages": pk}
    per: dict[str, list[int]] = {}  # coverage.py JSON format
    for fname, f in data["files"].items():
        parts = Path(fname).parts
        pkg = parts[parts.index("brayton_cycle") + 1] if len(parts) > 2 else "(top-level)"
        pkg = "(top-level)" if pkg.endswith(".py") else pkg
        s = per.setdefault(pkg, [0, 0])
        s[0] += f["summary"]["num_statements"]
        s[1] += f["summary"]["covered_lines"]
    ng = [v for k, v in per.items() if k != "gui"]
    return {"tool": tool, "total_percent": round(data["totals"]["percent_covered"], 1),
            "non_gui_percent": round(100 * sum(c for _, c in ng) / sum(s for s, _ in ng), 1),
            "packages": {k: round(100 * c / s, 1) for k, (s, c) in sorted(per.items())}}


# --------------------------------------------------------------- validation
def _row(case: str, qty: str, ref: float, got: float, rel: float, abs_: float = 0.0) -> dict:
    err = abs(got - ref)
    rel_err = err / abs(ref) if ref else None  # undefined for a zero reference (residual)
    tol = max(rel * abs(ref), abs_)
    return {"case": case, "quantity": qty, "reference": ref, "computed": got,
            "abs_error": err, "rel_error": rel_err, "tolerance": tol,
            "tolerance_rule": f"max({rel:g}·|ref|, {abs_:g})", "passed": err <= tol}


def run_validation(reference_file: Path = REFERENCE_FILE) -> dict[str, Any]:
    """Compare the solver with the independent reference data."""
    cases = json.loads(reference_file.read_text(encoding="utf-8"))["cases"]
    solver, rows = BraytonSolver(), []
    for name, short in (("A_ideal_cold_air", "A"), ("B_irreversible_variable_cp", "B")):
        ref, tol = cases[name]["expected"], cases[name]["tolerances"]
        r = solver.solve(BraytonConfig.from_reference_case(short, reference_file))
        if short == "A":
            t_rel = e_rel = tol["rel_tol_states_and_energies"]
            s_abs, h_abs = tol["abs_tol_s_gen"], 1e-6
        else:
            t_rel, e_rel = tol["rel_tol_temperatures"], tol["rel_tol_energies"]
            s_abs, h_abs = tol["abs_tol_entropy"], 1e-6
        for st in ref["states"]:
            got = r.states[st["label"]]
            rows.append(_row(short, f"T{st['label']} [K]", st["T"], got.T, t_rel))
            rows.append(_row(short, f"h{st['label']} [J/kg]", st["h"], got.h, e_rel, h_abs))
            rows.append(_row(short, f"s{st['label']} [J/(kg·K)]", st["s"], got.s, 0.0, s_abs))
        for q in ("w_c", "w_t", "w_net", "q_in", "q_out"):
            rows.append(_row(short, f"{q} [J/kg]", ref[q], getattr(r, q), e_rel))
        rows.append(_row(short, "BWR [-]", ref["bwr"], r.bwr, e_rel))
        rows.append(_row(short, "eta_th [-]", ref["eta_th"], r.eta_th, e_rel))
        if short == "B":
            rows.append(_row(short, "f [-]", ref["fuel_air_ratio"], r.fuel_air_ratio, e_rel))
            rows.append(_row(short, "SFC [kg/kWh]", ref["sfc_kg_per_kWh"], float(r.sfc or 0), e_rel))
            rows.append(_row(short, "W_net [W]", ref["net_power_W"], r.net_power, e_rel))
        for cv, v in ref["s_gen"].items():
            got_s = r.s_gen_total if cv == "total" else r.s_gen[cv]
            rows.append(_row(short, f"s_gen {cv} [J/(kg·K)]", v, got_s, e_rel, s_abs))
        rows.append(_row(short, "First-Law residual [-]", 0.0, r.first_law_residual, 0.0, 1e-6))
        if short == "A":
            an = ref["analytical"]
            rows.append(_row("A", "eta_th vs 1 - r_p^((1-γ)/γ)", an["eta_th_cold_air"], r.eta_th,
                             tol["rel_tol_vs_analytical_eta"]))
            opt = ParametricSweepEngine(solver).optimal_pressure_ratio(r.config, "w_net")
            rows.append(_row("A", "r_p,opt(w_net) vs analytic", an["rp_opt_w_net"],
                             opt.pressure_ratio, 1e-2))
            rows.append(_row("A", "w_net,max vs analytic [J/kg]", an["w_net_max"], opt.value, 1e-6))
    return {"rows": rows, "passed": sum(r["passed"] for r in rows), "total": len(rows),
            "all_passed": all(r["passed"] for r in rows),
            "cross_backend": run_cross_backend(cases["B_irreversible_variable_cp"]["tolerances"])}


def run_cross_backend(tol: dict[str, Any]) -> dict[str, Any]:
    """Case B KPIs with each installed backend vs the variable-cp backend."""
    base = BraytonConfig.from_reference_case("B")
    kpis = ("w_net", "eta_th", "fuel_air_ratio", "bwr")
    results: dict[str, Any] = {}
    for prov in ("variable", "coolprop", "cantera"):
        try:
            r = BraytonSolver().solve(base.replace(provider=prov))
        except BackendUnavailable:
            results[prov] = None
            continue
        results[prov] = {k: getattr(r, k) for k in kpis} | {"T4": r.states["4"].T}
    ref = results["variable"]
    rel_tol = tol["rel_tol_vs_coolprop_cantera"]
    comparisons = []
    for prov in ("coolprop", "cantera"):
        if results[prov] is None:
            continue
        for k, v in results[prov].items():
            rel = abs(v - ref[k]) / abs(ref[k])
            comparisons.append({"backend": prov, "kpi": k, "variable_cp": ref[k], "value": v,
                                "rel_diff": rel, "tolerance": rel_tol, "passed": rel <= rel_tol})
    return {"results": results, "comparisons": comparisons, "tolerance": rel_tol,
            "skipped": [p for p in ("coolprop", "cantera") if results[p] is None]}


# ------------------------------------------------------------------ runtime
def run_runtime(repeats: int = 7) -> dict[str, Any]:
    """Median wall-clock times (ms) of the main workloads."""
    base = BraytonConfig.from_reference_case("B")
    engine = ParametricSweepEngine()
    jobs: list[tuple[str, Any, int]] = []
    for prov in ALL_PROVIDERS:
        cfg = base.replace(provider=prov)
        try:
            BraytonSolver().solve(cfg)
        except BackendUnavailable:
            continue
        jobs.append((f"single_solve[{prov}]", lambda c=cfg: BraytonSolver().solve(c), 20))
    jobs += [
        ("sweep_1d[30 pts, variable]", lambda: engine.sweep_rp(base, n=30), 1),
        ("sweep_2d[12x8, variable]", lambda: engine.sweep_2d(base), 1),
        ("optimal_rp[w_net, variable]", lambda: engine.optimal_pressure_ratio(base, "w_net"), 1),
    ]
    timings = {}
    for name, fn, number in jobs:
        fn()  # warm-up (imports, caches)
        runs = [t / number * 1e3 for t in timeit.repeat(fn, repeat=repeats, number=number)]
        timings[name] = {"median_ms": statistics.median(runs), "min_ms": min(runs),
                         "max_ms": max(runs), "repeats": repeats, "number": number}
    return timings


def check_regressions(timings: dict[str, Any], baseline: dict[str, float],
                      factor: float = REGRESSION_FACTOR) -> list[str]:
    """Names of workloads whose median exceeds ``factor`` x the baseline median."""
    return [f"{k}: {v['median_ms']:.3f} ms > {factor:g} x baseline {baseline[k]:.3f} ms"
            for k, v in timings.items() if k in baseline and v["median_ms"] > factor * baseline[k]]


# ------------------------------------------------------------------ output
def _fmt(x: float) -> str:
    return f"{x:.6g}" if abs(x) < 1e6 else f"{x:.7g}"


def render_markdown(res: dict[str, Any], title: str = "Benchmark results") -> str:
    """Markdown rendering of the full results dict."""
    m, v, rt = res["machine"], res["validation"], res["runtime"]
    out = [f"# {title}", "",
           f"Generated {m['timestamp_utc']} · brayton_cycle {m['brayton_cycle']} · "
           f"Python {m['python']} ({m['implementation']}) · {m['platform']} · "
           f"{m['cpu_count']} CPU · numpy {m['numpy']} · scipy {m['scipy']}", ""]
    ver = res.get("verification")
    out += ["## a) Verification (pytest)", ""]
    if ver:
        out += ["| Tests | Passed | Failed | Errors | Skipped | Duration |", "|---|---|---|---|---|---|",
                f"| {ver['tests']} | {ver['passed']} | {ver['failed']} | {ver['errors']} | "
                f"{ver['skipped']} | {ver['duration_s']:.1f} s |", ""]
        if ver["skipped"]:
            have = [k for k, ok in m["optional_backends"].items() if ok]
            missing = [k for k, ok in m["optional_backends"].items() if not ok]
            out += [f"Skipped tests need the optional backends. Not installed: "
                    f"{', '.join(missing) or 'none'}; installed: {', '.join(have) or 'none'}.", ""]
        cov = ver.get("coverage")
        if cov:
            out += [f"**Line coverage** ({cov['tool']}): total **{cov['total_percent']} %**, "
                    f"non-GUI packages **{cov['non_gui_percent']} %**.", "",
                    "| Package | Coverage |", "|---|---|"]
            out += [f"| {k} | {p} % |" for k, p in cov["packages"].items()] + [""]
    else:
        out += ["Skipped (--skip-tests).", ""]
    out += ["## b) Validation against independent reference data", "",
            f"{v['passed']} / {v['total']} checks pass. Reference values come from "
            "`tools/generate_reference.py` (stdlib-only, independent of the solver). "
            "Pass if |computed − reference| ≤ tolerance.", ""]
    for case in ("A", "B"):
        out += [f"### Case {case}", "", "| Quantity | Reference | Computed | Abs error | Rel error | "
                "Tolerance | Pass |", "|---|---|---|---|---|---|---|"]
        for r in (x for x in v["rows"] if x["case"] == case):
            out.append(f"| {r['quantity']} | {_fmt(r['reference'])} | {_fmt(r['computed'])} | "
                       f"{r['abs_error']:.2e} | "
                       f"{'–' if r['rel_error'] is None else format(r['rel_error'], '.2e')} | "
                       f"{r['tolerance']:.2e} | "
                       f"{'✅' if r['passed'] else '❌'} |")
        out.append("")
    cb = v["cross_backend"]
    out += ["### Backend cross-check (Case B)", ""]
    if cb["comparisons"]:
        out += ["| Backend | KPI | variable-cp | Value | Rel diff | Tol | Pass |",
                "|---|---|---|---|---|---|---|"]
        out += [f"| {c['backend']} | {c['kpi']} | {_fmt(c['variable_cp'])} | {_fmt(c['value'])} | "
                f"{c['rel_diff']:.2e} | {c['tolerance']:.1e} | {'✅' if c['passed'] else '❌'} |"
                for c in cb["comparisons"]]
    if cb["skipped"]:
        out += [f"Not run for {', '.join(cb['skipped'])}: package not installed "
                "(`pip install -e \".[coolprop,cantera]\"`)."]
    out += ["", "## c) Runtime (timeit medians)", "",
            "| Workload | Median [ms] | Min [ms] | Max [ms] | Repeats × number | Baseline [ms] |",
            "|---|---|---|---|---|---|"]
    base = res.get("baseline", {})
    for k, t in rt.items():
        b = f"{base[k]:.3f}" if k in base else "–"
        out.append(f"| {k} | {t['median_ms']:.3f} | {t['min_ms']:.3f} | {t['max_ms']:.3f} | "
                   f"{t['repeats']} × {t['number']} | {b} |")
    reg = res.get("regressions", [])
    out += ["", f"Regression rule: fail only if a median exceeds {REGRESSION_FACTOR:g} × baseline. "
            + ("**Regressions:** " + "; ".join(reg) if reg else "No regressions."), ""]
    return "\n".join(out)


def write_validation_report(res: dict[str, Any], path: Path = VALIDATION_DOC) -> Path:
    """Write docs/validation_report.md (methodology + generated tables)."""
    intro = (
        "> Generated by `benchmarks/run_benchmarks.py`. Re-run it to refresh this report.\n\n"
        "**Method.** Two reference cases are solved and compared with values from "
        "`tools/generate_reference.py`. That script uses only the standard library and "
        "re-types its inputs from the primary sources, so the comparison is not circular. "
        "Case A (ideal cold-air) must match closed-form results to round-off; Case B "
        "(irreversible, Table A-2c variable cp) to the root-finder tolerance. Property "
        "differences against Çengel Table A-17 are tested separately in "
        "`tests/test_properties.py` (worst case 0.28 % against a 1 % limit).\n")
    text = render_markdown(res, "Validation report").replace("\n## a)", "\n" + intro + "\n## a)", 1)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run all benchmark steps; returns 0 on success, 1 on any failure."""
    p = argparse.ArgumentParser(description="Brayton cycle verification and benchmarks")
    p.add_argument("--skip-tests", action="store_true", help="skip the pytest/coverage step")
    p.add_argument("--no-coverage", action="store_true", help="run pytest without coverage")
    p.add_argument("--repeats", type=int, default=7, help="timeit repeats per workload")
    p.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--baseline", type=Path, default=BASELINE_FILE,
                   help="baseline timings file (created on first run if missing)")
    p.add_argument("--update-baseline", action="store_true",
                   help="store these timings as the new baseline")
    p.add_argument("--no-report-doc", action="store_true",
                   help="do not rewrite docs/validation_report.md")
    args = p.parse_args(argv)

    res: dict[str, Any] = {"machine": machine_info()}
    if not args.skip_tests:
        print("a) running pytest ...", flush=True)
        res["verification"] = run_verification(coverage=not args.no_coverage)
        print("   " + res["verification"]["summary_line"])
    print("b) validation ...", flush=True)
    res["validation"] = run_validation()
    print(f"   {res['validation']['passed']}/{res['validation']['total']} checks pass")
    print("c) runtime ...", flush=True)
    res["runtime"] = run_runtime(args.repeats)
    baseline = (json.loads(args.baseline.read_text())["median_ms"]
                if args.baseline.exists() else {})
    if args.update_baseline or not baseline:
        args.baseline.write_text(json.dumps(
            {"machine": res["machine"], "median_ms": {k: v["median_ms"]
                                                      for k, v in res["runtime"].items()}},
            indent=2) + "\n", encoding="utf-8")
        baseline = {k: v["median_ms"] for k, v in res["runtime"].items()}
    res["baseline"] = baseline
    res["regressions"] = check_regressions(res["runtime"], baseline)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "benchmark_results.json").write_text(
        json.dumps(res, indent=2, default=str, allow_nan=False), encoding="utf-8")
    (args.output_dir / "benchmark_results.md").write_text(render_markdown(res) + "\n",
                                                           encoding="utf-8")
    if not args.no_report_doc:
        write_validation_report(res)
    for k, t in res["runtime"].items():
        print(f"   {k:<32} {t['median_ms']:9.3f} ms")
    ok_tests = args.skip_tests or (res["verification"]["failed"] == 0
                                   and res["verification"]["errors"] == 0)
    ok_cb = all(c["passed"] for c in res["validation"]["cross_backend"]["comparisons"])
    ok = ok_tests and res["validation"]["all_passed"] and ok_cb and not res["regressions"]
    print(f"\nresults: {args.output_dir / 'benchmark_results.md'}")
    print("OVERALL: PASS" if ok else "OVERALL: FAIL " + "; ".join(res["regressions"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
