# Benchmarks

`run_benchmarks.py` runs three steps. You can start it in three ways: `python benchmarks/run_benchmarks.py`,
`python run_verification_and_benchmarks.py`, or `python main.py --benchmark`.

1. **Verification:** runs the full pytest suite and reports pass/fail/skip counts. It also measures line
   coverage, with pytest-cov if installed, otherwise with `tools/stdlib_coverage.py`.
2. **Validation:** compares Case A and Case B with `validation_reference_data.json` and reports absolute
   error, relative error, tolerance and pass/fail. It also checks against analytic cold-air results, and
   compares variable-cp, CoolProp and Cantera when those are installed.
3. **Runtime:** records timeit medians for one solve per backend, a 30-point 1-D sweep, a 12 × 8 2-D sweep
   and an optimal-r_p search.

Outputs:
- `results/benchmark_results.json` and `results/benchmark_results.md`, including machine and library info.
- `docs/validation_report.md`, which is refreshed on each run.

The exit code is non-zero if a test fails, a validation check is out of tolerance, a cross-backend check
fails, or a runtime median exceeds **10×** the baseline in `baseline.json`.

Useful options:

| Option | Effect |
|---|---|
| `--skip-tests` | Skip the pytest step |
| `--no-coverage` | Run pytest without coverage |
| `--repeats N` | Set the number of timeit repeats |
| `--update-baseline` | Store the current timings as the new baseline (do this after an intentional performance change or on new hardware) |
| `--baseline PATH` | Use a different baseline file |
| `--no-report-doc` | Do not rewrite `docs/validation_report.md` |
