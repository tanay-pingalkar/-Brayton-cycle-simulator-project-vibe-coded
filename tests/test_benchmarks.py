"""Benchmark harness tests (REQ-V01): validation table, regression rule, outputs.

The full harness (pytest inside pytest) is not run here; ``main`` is called
with ``--skip-tests`` and one timeit repeat into a temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import run_benchmarks as rb
from brayton_cycle import cli


def test_validation_all_rows_pass() -> None:
    v = rb.run_validation()
    assert v["all_passed"] and v["passed"] == v["total"] > 60
    cases = {r["case"] for r in v["rows"]}
    assert cases == {"A", "B"}
    opt = next(r for r in v["rows"] if r["quantity"].startswith("r_p,opt"))
    assert opt["rel_error"] < 1e-4


def test_cross_backend_reports_skips_cleanly() -> None:
    cb = rb.run_cross_backend({"rel_tol_vs_coolprop_cantera": 1.5e-2})
    assert cb["results"]["variable"] is not None
    for prov in cb["skipped"]:
        assert cb["results"][prov] is None


def test_regression_rule_only_fires_above_factor() -> None:
    timings = {"a": {"median_ms": 9.0}, "b": {"median_ms": 11.0}, "c": {"median_ms": 50.0}}
    baseline = {"a": 1.0, "b": 1.0}
    assert rb.check_regressions(timings, baseline) == [
        "b: 11.000 ms > 10 x baseline 1.000 ms"]


def test_main_writes_results(tmp_path: Path) -> None:
    code = rb.main(["--skip-tests", "--repeats", "1", "--output-dir", str(tmp_path),
                    "--no-report-doc", "--baseline", str(tmp_path / "baseline.json")])
    assert code == 0
    assert (tmp_path / "baseline.json").exists()
    data = json.loads((tmp_path / "benchmark_results.json").read_text(encoding="utf-8"))
    assert {"machine", "validation", "runtime", "baseline", "regressions"} <= set(data)
    assert "single_solve[variable]" in data["runtime"]
    assert "sweep_2d[12x8, variable]" in data["runtime"]
    assert data["machine"]["python"]
    md = (tmp_path / "benchmark_results.md").read_text(encoding="utf-8")
    assert "## b) Validation" in md and "## c) Runtime" in md and "❌" not in md


def test_cli_benchmark_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_run_benchmarks", lambda: 0)
    assert cli.main(["--benchmark"]) == 0
