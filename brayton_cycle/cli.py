"""Headless command-line interface (REQ-U01).

Examples::

    python main.py --case B
    python main.py --case A --provider constant --output-dir out/ --plots
    python main.py --gui
    python main.py --benchmark
    python main.py --config my_case.json --mode sweep --sweep-param pressure_ratio \\
                   --sweep-start 2 --sweep-stop 40 --sweep-num 20 --output-dir out/

Exit codes:
    0  success
    1  ConservationError / SecondLawViolation (an audit failed)
    2  command-line usage error (argparse), or GUI requested but Tk is unavailable
    3  invalid input or configuration (validation failure, unreadable file)
    4  requested property backend not installed
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

import numpy as np

from brayton_cycle import __version__
from brayton_cycle.core.exceptions import (
    BackendUnavailable,
    BraytonError,
    ConservationError,
    SecondLawViolation,
)
from brayton_cycle.solver import BraytonConfig, BraytonResult, BraytonSolver

EXIT_OK, EXIT_AUDIT, EXIT_USAGE, EXIT_INPUT, EXIT_BACKEND = 0, 1, 2, 3, 4
PROVIDER_CHOICES = ("constant", "variable", "coolprop", "cantera")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    p = argparse.ArgumentParser(prog="brayton", description="Brayton gas-turbine cycle simulator",
                                epilog="Exit codes: 0 ok, 1 audit failed, 2 usage, "
                                       "3 invalid input, 4 backend missing.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--config", type=Path, help="JSON file with one BraytonConfig object")
    src.add_argument("--case", help="reference case from validation_reference_data.json (A or B)")
    p.add_argument("--provider", choices=PROVIDER_CHOICES, help="override the property backend")
    p.add_argument("--mode", choices=("single", "sweep"), default="single")
    p.add_argument("--output-dir", type=Path, help="write result.json / sweep.csv here")
    p.add_argument("--plots", action="store_true",
                   help="with --output-dir: also save PNG figures (T-s, P-v, audit, sweep)")
    p.add_argument("--gui", action="store_true", help="launch the Tkinter GUI")
    p.add_argument("--benchmark", action="store_true",
                   help="run verification, validation and runtime benchmarks "
                        "(benchmarks/run_benchmarks.py; repository checkout only)")
    sw = p.add_argument_group("sweep options (--mode sweep)")
    sw.add_argument("--sweep-param", default="pressure_ratio")
    sw.add_argument("--sweep-start", type=float, default=2.0)
    sw.add_argument("--sweep-stop", type=float, default=40.0)
    sw.add_argument("--sweep-num", type=int, default=20)
    return p


# ------------------------------------------------------------------ output
def format_result(r: BraytonResult) -> str:
    """Human-readable tables (display units from ``reporting.tables``).

    Args:
        r: Solved cycle result.

    Returns:
        Multi-line text with the station table and KPIs.
    """
    from brayton_cycle.reporting import STATION_HEADERS, kpi_rows, station_rows

    widths = (7, 10, 11, 11, 14)
    head = " ".join(f"{h:>{w}}" for h, w in zip(STATION_HEADERS, widths))
    lines = [f"Brayton cycle  [{r.config.name or 'custom'}]  provider: {r.provider_name}", "",
             head, "-" * len(head)]
    lines += [" ".join(f"{c:>{w}}" for c, w in zip(row, widths)) for row in station_rows(r)]
    lines += ["", "-" * len(head)] + [f"{k:<22} {v}" for k, v in kpi_rows(r)]
    return "\n".join(lines)


def _run_single(cfg: BraytonConfig, args: argparse.Namespace, out: TextIO) -> None:
    result = BraytonSolver().solve(cfg)
    print(format_result(result), file=out)
    if args.output_dir is not None:
        from brayton_cycle.reporting import ReportGenerator

        args.output_dir.mkdir(parents=True, exist_ok=True)
        path = args.output_dir / "result.json"
        path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        paths = ReportGenerator().write_all(result, args.output_dir, figures=args.plots)
        print(f"\nwrote {path}", file=out)
        for p in paths.values():
            print(f"wrote {p}", file=out)


def _run_sweep(cfg: BraytonConfig, args: argparse.Namespace, out: TextIO) -> None:
    from brayton_cycle.analysis import ParametricSweepEngine

    engine = ParametricSweepEngine()
    values = np.linspace(args.sweep_start, args.sweep_stop, args.sweep_num)
    df = engine.sweep_1d(cfg, args.sweep_param, values)
    show = df[[args.sweep_param, "w_net", "eta_th", "bwr", "sfc_kg_per_kWh", "status"]].copy()
    show["w_net"] = show["w_net"] / 1e3
    show = show.rename(columns={"w_net": "w_net [kJ/kg]", "sfc_kg_per_kWh": "SFC [kg/kWh]"})
    show["status"] = show["status"].str.slice(0, 40)
    print(show.to_string(index=False, float_format=lambda x: f"{x:.4f}"), file=out)
    optima: dict[str, float] = {}
    if args.sweep_param == "pressure_ratio":
        lo, hi = max(1.0001, args.sweep_start), args.sweep_stop
        for obj in ("w_net", "eta_th"):
            o = engine.optimal_pressure_ratio(cfg, obj, bounds=(lo, hi))
            optima[obj] = o.pressure_ratio
            val = f"{o.value / 1e3:.3f} kJ/kg" if obj == "w_net" else f"{100 * o.value:.3f} %"
            note = "  (at search bound)" if o.at_bound else ""
            print(f"optimal r_p for {obj:<6}: {o.pressure_ratio:.4f}  ->  {val}{note}", file=out)
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        path = args.output_dir / "sweep.csv"
        df.to_csv(path, index=False)
        print(f"\nwrote {path}", file=out)
        if args.plots:
            from brayton_cycle.reporting import CyclePlotter

            fig = CyclePlotter().sweep_1d(df, args.sweep_param, optima=optima)
            fig.savefig(args.output_dir / "sweep.png", dpi=150)
            print(f"wrote {args.output_dir / 'sweep.png'}", file=out)


def _run_benchmarks() -> int:
    """Run benchmarks/run_benchmarks.py from a repository checkout.

    Returns:
        The benchmark script's exit code, or ``EXIT_USAGE`` if the script is not
        present (e.g. an installed wheel without the repository).
    """
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "benchmarks" / "run_benchmarks.py"
    if not script.is_file():
        print(f"benchmark script not found at {script}; run from a repository checkout.",
              file=sys.stderr)
        return EXIT_USAGE
    spec = importlib.util.spec_from_file_location("brayton_benchmarks", script)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return int(module.main([]))


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    """CLI entry point; returns the process exit code.

    Args:
        argv: Command-line arguments (``sys.argv[1:]`` if None).
        out: Stream for normal output (``sys.stdout`` if None).

    Returns:
        Process exit code (see module docstring).
    """
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.benchmark:
        return _run_benchmarks()
    if args.gui:
        try:
            from brayton_cycle.gui import launch

            launch()
        except ImportError as exc:  # tkinter missing (e.g. headless Python build)
            print(f"GUI unavailable: {exc}. Install Tk for your Python "
                  "(e.g. apt install python3-tk) or use the CLI.", file=sys.stderr)
            return EXIT_USAGE
        return EXIT_OK
    try:
        if args.config is not None:
            cfg = BraytonConfig.from_json(args.config)
        else:
            cfg = BraytonConfig.from_reference_case(args.case or "B")
        if args.provider:
            new = cfg.replace(provider=args.provider)
            # backend-specific options (e.g. cp, gamma) do not carry over to another backend
            cfg = new if new.provider == cfg.provider else new.replace(provider_options={})
        if args.mode == "single":
            _run_single(cfg, args, out)
        else:
            _run_sweep(cfg, args, out)
    except (ConservationError, SecondLawViolation) as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        return EXIT_AUDIT
    except BackendUnavailable as exc:
        print(f"BACKEND UNAVAILABLE: {exc}", file=sys.stderr)
        return EXIT_BACKEND
    except (BraytonError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID INPUT: {exc}", file=sys.stderr)
        return EXIT_INPUT
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
