#!/usr/bin/env python3
"""Run verification (pytest + coverage), validation and runtime benchmarks.

Equivalent to ``python benchmarks/run_benchmarks.py`` and ``python main.py --benchmark``.
Options are passed through, e.g. ``--skip-tests --repeats 3``.
"""

from __future__ import annotations

import sys

from benchmarks.run_benchmarks import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
