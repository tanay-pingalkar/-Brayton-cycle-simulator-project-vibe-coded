"""ReportGenerator: JSON and Markdown reports of a solved cycle (REQ-R01)."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from brayton_cycle import __version__
from brayton_cycle.analysis import OptimumResult
from brayton_cycle.core.constants import FIRST_LAW_RESIDUAL_TOL
from brayton_cycle.reporting.citations import property_citation
from brayton_cycle.reporting.tables import (STATION_HEADERS, input_rows, kpi_rows, optimum_rows,
                                            station_rows)
from brayton_cycle.solver import BraytonResult

ASSUMPTIONS: tuple[str, ...] = (
    "Steady flow; kinetic and potential energy neglected; adiabatic compressor and turbine.",
    "Air-standard: working fluid is air throughout; fuel mass and combustion products are "
    "not modelled (docs/physics_formulation.md §1).",
    "Entropy generation uses T_source = T3 and T_sink = T1 unless overridden (§6).",
    "P4 = P1 (no exhaust loss); combustor loss P3 = P2 (1 - dP_comb).",
)


def _md_table(headers: tuple[str, ...] | list[str], rows: list[tuple[str, ...]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


class ReportGenerator:
    """Write a solved ``BraytonResult`` as JSON and/or Markdown."""

    def build(self, r: BraytonResult,
              optima: dict[str, OptimumResult] | None = None) -> dict[str, Any]:
        """Report content as a JSON-serialisable dict (SI units).

        Args:
            r: Solved cycle result.
            optima: Optional optimal-r_p results keyed by objective.

        Returns:
            JSON-serialisable dict.
        """
        d = r.to_dict()
        d["metadata"] = {
            "generator": f"brayton_cycle {__version__}",
            "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "case": r.config.name or "custom",
        }
        d["property_data"] = property_citation(r.provider_name)
        d["audits"] = {
            "first_law_residual": r.first_law_residual,
            "first_law_limit": FIRST_LAW_RESIDUAL_TOL,
            "first_law_pass": r.first_law_residual < FIRST_LAW_RESIDUAL_TOL,
            "second_law_pass": all(v >= -1e-9 for v in r.s_gen.values()),
        }
        d["assumptions"] = list(ASSUMPTIONS)
        if optima:
            d["optima"] = {k: {"pressure_ratio": o.pressure_ratio, "value": o.value,
                               "bounds": list(o.bounds), "at_bound": o.at_bound}
                           for k, o in optima.items()}
        return d

    def write_json(self, r: BraytonResult, path: str | Path,
                   optima: dict[str, OptimumResult] | None = None) -> Path:
        """Write the JSON report; returns the path.

        Args:
            r: Solved cycle result.
            path: Destination JSON file.
            optima: Optional optimal-r_p results keyed by objective.

        Returns:
            Path written.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.build(r, optima), indent=2, allow_nan=False), encoding="utf-8")
        return p

    def markdown(self, r: BraytonResult, optima: dict[str, OptimumResult] | None = None,
                 figures: dict[str, str] | None = None) -> str:
        """Markdown report text. ``figures`` maps caption -> relative image path.

        Args:
            r: Solved cycle result.
            optima: Optional optimal-r_p results keyed by objective.
            figures: Caption -> relative image path to embed.

        Returns:
            Markdown text.
        """
        d = self.build(r, optima)
        a, pd_ = d["audits"], d["property_data"]
        ok = lambda b: "PASS" if b else "FAIL"  # noqa: E731
        parts = [
            f"# Brayton cycle report: {d['metadata']['case']}",
            f"Generated {d['metadata']['created_utc']} by {d['metadata']['generator']}.",
            "## Inputs", _md_table(["Input", "Value"], input_rows(r)),
            "## States", _md_table(list(STATION_HEADERS), station_rows(r)),
            "## Key performance indicators", _md_table(["KPI", "Value"], kpi_rows(r)),
            "## Audits",
            _md_table(["Check", "Value", "Result"], [
                ("First-Law residual", f"{a['first_law_residual']:.2e} (limit {a['first_law_limit']:.0e})",
                 ok(a["first_law_pass"])),
                *[(f"s_gen {k}", f"{v:.3f} J/(kg·K)", ok(v >= -1e-9)) for k, v in r.s_gen.items()],
            ]),
        ]
        if optima:
            parts += ["## Optimal pressure ratio", _md_table(
                ["Objective", "r_p,opt", "Value", "Note"], optimum_rows(optima))]
        if figures:
            parts += ["## Figures"] + [f"![{cap}]({path})" for cap, path in figures.items()]
        parts += ["## Assumptions", "\n".join(f"- {x}" for x in ASSUMPTIONS),
                  "## Property data", f"Backend **{pd_['backend']}**: {pd_['description']}.",
                  "\n".join(f"- {ref}" for ref in pd_["references"])]
        return "\n\n".join(parts) + "\n"

    def write_markdown(self, r: BraytonResult, path: str | Path,
                       optima: dict[str, OptimumResult] | None = None,
                       figures: dict[str, str] | None = None) -> Path:
        """Write the Markdown report; returns the path.

        Args:
            r: Solved cycle result.
            path: Destination Markdown file.
            optima: Optional optimal-r_p results keyed by objective.
            figures: Caption -> relative image path to embed.

        Returns:
            Path written.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.markdown(r, optima, figures), encoding="utf-8")
        return p

    def write_all(self, r: BraytonResult, out_dir: str | Path, *, figures: bool = True,
                  optima: dict[str, OptimumResult] | None = None,
                  stem: str = "report") -> dict[str, Path]:
        """Write report.json, report.md and (optionally) PNG figures into ``out_dir``.

        Args:
            r: Solved cycle result.
            out_dir: Destination folder.
            figures: Also render and save the PNG figures.
            optima: Optional optimal-r_p results keyed by objective.
            stem: Base file name of the reports.

        Returns:
            Mapping of artefact name -> path.
        """
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        captions: dict[str, str] = {}
        if figures:
            from brayton_cycle.reporting.plots import CyclePlotter

            plotter = CyclePlotter()
            for key, cap, fn in (("ts", "T-s diagram", plotter.ts_diagram),
                                 ("pv", "P-v diagram", plotter.pv_diagram),
                                 ("energy_audit", "Energy audit", plotter.energy_audit)):
                fig = fn(r)
                paths[key] = out / f"{key}.png"
                fig.savefig(paths[key], dpi=150)
                captions[cap] = paths[key].name
        paths["json"] = self.write_json(r, out / f"{stem}.json", optima)
        paths["markdown"] = self.write_markdown(r, out / f"{stem}.md", optima, captions)
        return paths
