#!/usr/bin/env python3
"""Line coverage for brayton_cycle using only the standard library (Python >= 3.12).

Used when ``pytest-cov``/``coverage.py`` is not installed (e.g. offline CI).
It runs pytest in-process with a ``sys.monitoring`` LINE hook and compares the
executed lines with the executable lines of every module (taken from the
compiled code objects' ``co_lines()``, the same source coverage.py relies on).
Lines marked ``# pragma: no cover`` are excluded. Code run in subprocesses
(e.g. ``main.py`` smoke tests) is not counted, which matches coverage.py
without its subprocess plugin. Figures normally agree with
``pytest --cov=brayton_cycle`` to within a few percent.

Usage:
    python tools/stdlib_coverage.py [--json PATH] [pytest args...]
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "brayton_cycle"


def executable_lines(path: Path) -> set[int]:
    """Line numbers that carry bytecode in ``path`` (minus ``pragma: no cover`` lines)."""
    src = path.read_text(encoding="utf-8")
    skip = {i for i, line in enumerate(src.splitlines(), 1) if "pragma: no cover" in line}
    lines: set[int] = set()
    stack: list[types.CodeType] = [compile(src, str(path), "exec")]
    while stack:
        code = stack.pop()
        lines.update(ln for _, _, ln in code.co_lines() if ln is not None)
        stack.extend(c for c in code.co_consts if isinstance(c, types.CodeType))
    lines.discard(0)
    return lines - skip


def run(pytest_args: list[str]) -> tuple[int, dict[str, set[int]]]:
    """Run pytest with a LINE monitor; returns (pytest exit code, file -> executed lines)."""
    import pytest

    mon = sys.monitoring
    tool = mon.COVERAGE_ID
    hits: dict[str, set[int]] = defaultdict(set)
    prefix = str(PKG)

    def on_line(code: types.CodeType, line: int) -> object:
        if code.co_filename.startswith(prefix):
            hits[code.co_filename].add(line)
        return mon.DISABLE  # each location reported once: near-zero overhead afterwards

    mon.use_tool_id(tool, "brayton-stdlib-coverage")
    mon.register_callback(tool, mon.events.LINE, on_line)
    mon.set_events(tool, mon.events.LINE)
    try:
        code = pytest.main(pytest_args)
    finally:
        mon.set_events(tool, 0)
        mon.register_callback(tool, mon.events.LINE, None)
        mon.free_tool_id(tool)
    return int(code), hits


def summarise(hits: dict[str, set[int]]) -> dict[str, object]:
    """Per-file and per-package statement coverage."""
    files, packages = {}, defaultdict(lambda: [0, 0])
    for path in sorted(PKG.rglob("*.py")):
        exe = executable_lines(path)
        run_ = exe & hits.get(str(path), set())
        rel = str(path.relative_to(ROOT))
        files[rel] = {"statements": len(exe), "covered": len(run_),
                      "percent": 100.0 * len(run_) / len(exe) if exe else 100.0,
                      "missing": sorted(exe - run_)}
        parts = path.relative_to(PKG).parts
        pkg = parts[0] if len(parts) > 1 else "(top-level)"
        packages[pkg][0] += len(exe)
        packages[pkg][1] += len(run_)
    tot_s = sum(v[0] for v in packages.values())
    tot_c = sum(v[1] for v in packages.values())
    non_gui = [v for k, v in packages.items() if k != "gui"]
    ng_s, ng_c = sum(v[0] for v in non_gui), sum(v[1] for v in non_gui)
    return {
        "tool": "tools/stdlib_coverage.py (sys.monitoring)",
        "total_percent": 100.0 * tot_c / tot_s,
        "non_gui_percent": 100.0 * ng_c / ng_s,
        "packages": {k: {"statements": s, "covered": c, "percent": 100.0 * c / s}
                     for k, (s, c) in sorted(packages.items())},
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--json", type=Path, help="write the summary as JSON")
    args, rest = p.parse_known_args(argv)
    sys.path.insert(0, str(ROOT))
    code, hits = run(rest or ["-q", "-p", "no:cacheprovider", str(ROOT / "tests")])
    summary = summarise(hits)
    print(f"\n{'Package':<16}{'Stmts':>7}{'Cover':>9}")
    for k, v in summary["packages"].items():  # type: ignore[union-attr]
        print(f"{k:<16}{v['statements']:>7}{v['percent']:>8.1f}%")
    print(f"{'TOTAL':<16}{'':>7}{summary['total_percent']:>8.1f}%   "
          f"(non-GUI: {summary['non_gui_percent']:.1f}%)")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
