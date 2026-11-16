"""Figures and reports (REQ-R01)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from matplotlib.figure import Figure

from brayton_cycle.analysis import ParametricSweepEngine
from brayton_cycle.reporting import CyclePlotter, ReportGenerator, property_citation
from brayton_cycle.reporting.citations import PROPERTY_DATA, REFERENCES
from brayton_cycle.solver import BraytonConfig, BraytonSolver

ROOT = Path(__file__).resolve().parents[1]
CFG = BraytonConfig.from_reference_case("B")
RESULT = BraytonSolver().solve(CFG)
ENGINE = ParametricSweepEngine()
PLOT = CyclePlotter(n_points=20)


def _labels(fig: Figure) -> list[tuple[str, str]]:
    return [(ax.get_xlabel(), ax.get_ylabel()) for ax in fig.axes]


# --------------------------------------------------------------- figures
def test_ts_diagram_axes() -> None:
    fig = PLOT.ts_diagram(RESULT)
    assert isinstance(fig, Figure) and len(fig.axes) == 1
    xl, yl = _labels(fig)[0]
    assert "s [kJ/(kg·K)]" in xl and "T [K]" in yl
    ax = fig.axes[0]
    assert len(ax.get_lines()) >= 4 + 2  # 4 process paths + 2 isentropic segments
    texts = {t.get_text() for t in ax.texts}
    assert {"1", "2", "2s", "3", "4", "4s"} <= texts


def test_ts_path_passes_through_states() -> None:
    fig = PLOT.ts_diagram(RESULT)
    xs, ys = fig.axes[0].get_lines()[1].get_data()  # combustor isobar 2 -> 3
    assert ys[0] == pytest.approx(RESULT.states["2"].T) and ys[-1] == pytest.approx(1500.0)
    assert xs[-1] == pytest.approx(RESULT.states["3"].s / 1e3, rel=1e-9)


def test_pv_diagram_axes_and_log_scale() -> None:
    fig = PLOT.pv_diagram(RESULT)
    xl, yl = _labels(fig)[0]
    assert "v [m³/kg]" in xl and "P [kPa]" in yl
    assert fig.axes[0].get_xscale() == "log" and fig.axes[0].get_yscale() == "log"
    assert PLOT.pv_diagram(RESULT, log=False).axes[0].get_xscale() == "linear"


def test_energy_audit_axes() -> None:
    fig = PLOT.energy_audit(RESULT)
    assert len(fig.axes) == 2
    (_, e_label), (_, s_label) = _labels(fig)
    assert "[kJ/kg]" in e_label and "[J/(kg·K)]" in s_label
    heights = [p.get_height() for p in fig.axes[0].patches]
    assert heights == pytest.approx([v / 1e3 for v in
                                     (RESULT.w_c, RESULT.w_t, RESULT.w_net, RESULT.q_in, RESULT.q_out)])


def test_sweep_plot_one_panel_per_kpi_no_twin_axes() -> None:
    df = ENGINE.sweep_rp(CFG, n=10)
    fig = PLOT.sweep_1d(df, optima={"w_net": 13.85, "eta_th": 37.7})
    assert len(fig.axes) == 2  # stacked panels, never a dual y-axis
    assert fig.axes[-1].get_xlabel() == "Pressure ratio r_p [-]"
    assert "[kJ/kg]" in fig.axes[0].get_ylabel() and "[%]" in fig.axes[1].get_ylabel()


def test_contour_axes_and_colorbar() -> None:
    fig = PLOT.contour_2d(ENGINE.sweep_2d(CFG, rp_values=[4, 10, 20, 30], T3_values=[1200, 1400, 1600]))
    assert len(fig.axes) == 2  # main + colorbar
    xl, yl = _labels(fig)[0]
    assert xl == "Pressure ratio r_p [-]" and yl == "T3 [K]"
    assert "[kJ/kg]" in fig.axes[1].get_ylabel()


def test_figures_save_without_pyplot(tmp_path: Path) -> None:
    p = tmp_path / "ts.png"
    PLOT.ts_diagram(RESULT).savefig(p)
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_reporting_does_not_import_pyplot() -> None:
    import ast

    for f in (ROOT / "brayton_cycle" / "reporting").glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any("pyplot" in n for n in names), f.name


# --------------------------------------------------------------- reports
def test_write_all_creates_parseable_files(tmp_path: Path) -> None:
    optima = {o: ENGINE.optimal_pressure_ratio(CFG, o) for o in ("w_net", "eta_th")}
    paths = ReportGenerator().write_all(RESULT, tmp_path, optima=optima)
    assert set(paths) == {"ts", "pv", "energy_audit", "json", "markdown"}
    assert all(p.exists() and p.stat().st_size > 0 for p in paths.values())
    d = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert d["provider"] == "variable-cp"
    assert d["audits"]["first_law_pass"] and d["audits"]["first_law_residual"] < 1e-6
    assert d["kpis"]["eta_th"] == pytest.approx(RESULT.eta_th)
    assert d["config"]["pressure_ratio"] == 14.0
    assert "Table A-2c" in d["property_data"]["description"]
    assert d["property_data"]["references"][0].startswith("[1] Çengel")
    assert d["optima"]["w_net"]["pressure_ratio"] == pytest.approx(optima["w_net"].pressure_ratio)
    md = paths["markdown"].read_text(encoding="utf-8")
    for heading in ("## Inputs", "## States", "## Key performance indicators", "## Audits",
                    "## Optimal pressure ratio", "## Figures", "## Property data"):
        assert heading in md
    assert "| 2s |" in md and "PASS" in md and "![T-s diagram](ts.png)" in md
    assert re.search(r"First-Law residual \| [0-9.e+-]+ \(limit", md)


def test_markdown_tables_are_well_formed(tmp_path: Path) -> None:
    md = ReportGenerator().write_markdown(RESULT, tmp_path / "r.md").read_text(encoding="utf-8")
    for block in md.split("\n\n"):
        lines = block.splitlines()
        if lines and lines[0].startswith("|"):
            assert len({line.count("|") for line in lines}) == 1, block


def test_json_only_without_figures(tmp_path: Path) -> None:
    paths = ReportGenerator().write_all(RESULT, tmp_path, figures=False)
    assert set(paths) == {"json", "markdown"}


@pytest.mark.parametrize("backend", sorted(PROPERTY_DATA))
def test_property_citations_resolve(backend: str) -> None:
    c = property_citation(backend)
    assert c["references"] and not str(c["description"]).startswith("[FLAG")


def test_unknown_backend_citation_is_flagged() -> None:
    assert str(property_citation("mystery")["description"]).startswith("[FLAG")


def test_citations_consistent_with_references_md() -> None:
    refs = (ROOT / "docs" / "references.md").read_text(encoding="utf-8")
    for tag, entry in REFERENCES.items():
        assert f"[{tag}]" in refs
        assert entry.split(",")[0] in refs  # first author surname
        doi = re.search(r"https://doi\.org/\S+", entry)
        if doi:
            assert doi.group(0) in refs
